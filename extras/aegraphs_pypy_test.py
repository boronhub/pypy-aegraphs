#import sys
from rpython.jit.metainterp.history import ConstInt
from rpython.jit.metainterp.optimize import InvalidLoop
from rpython.jit.metainterp.optimizeopt.intutils import IntBound
from rpython.jit.metainterp.optimizeopt.optimizer import Optimization, CONST_1, CONST_0
from rpython.jit.metainterp.optimizeopt.util import (
    make_dispatcher_method,
    have_dispatcher_method,
    get_box_replacement,
)
from rpython.jit.metainterp.optimizeopt.info import getptrinfo
from rpython.jit.metainterp.resoperation import rop
from rpython.jit.metainterp.optimizeopt import vstring
from rpython.jit.metainterp.optimizeopt import autogenintrules
from rpython.jit.codewriter.effectinfo import EffectInfo
from rpython.rlib.rarithmetic import intmask
from rpython.rlib.debug import debug_print
from rpython.rlib import objectmodel

import itertools
import networkx as nx


import pytest
from rpython.jit.metainterp.optimizeopt.test.test_optimizebasic import BaseTestBasic
from rpython.jit.metainterp.optimizeopt.intutils import MININT, MAXINT
from rpython.jit.metainterp.optimizeopt.intdiv import magic_numbers
from rpython.rlib.rarithmetic import intmask, LONG_BIT


class EId(int):
    pass


class ELit(object):
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, ELit) and self.value == other.value

    def __hash__(self):
        return hash(self.value)

    def __repr__(self):
        return "ELit(%r)" % self.value


class Enode(object):
    def __init__(self, name, args):
        self.name = name
        self.args = tuple(args)

    def __eq__(self, other):
        return (
            isinstance(other, Enode)
            and self.name == other.name
            and self.args == other.args
        )

    def __hash__(self):
        return hash((self.name, self.args))

    def __repr__(self):
        return "Enode(%r, %r)" % (self.name, self.args)


class AEGraph(object):
    def __init__(self):
        self.uf = []
        self.unodes = []
        self.enodes = []
        self.hashcons = {}

    def __repr__(self):
        return "AEGraph: {{\nuf = {},\nunodes = {},\nenodes = {},\nhashcons = {}\n}}".format(
            self.uf, self.unodes, self.enodes, self.hashcons
        )

    def makeset(self):
        z = len(self.uf)
        self.uf.append(z)
        self.unodes.append(None)
        self.enodes.append(None)
        return EId(z)

    def find(self, x):
        while self.uf[x] != x:
            x = self.uf[x]
        return x

    def union(self, x, y):
        assert isinstance(x, int) and isinstance(y, int)
        x = self.find(x)
        y = self.find(y)
        if x != y:
            z = self.makeset()
            self.uf[x] = z
            self.uf[y] = z
            self.unodes[z] = (x, y)
            return z
        else:
            return x

    def enum(self, x):
        if self.unodes[x] is None:
            yield x
        elif isinstance(self.unodes[x], tuple):
            l, r = self.unodes[x]
            for e in self.enum(l):
                yield e
            for e in self.enum(r):
                yield e
        else:
            raise ValueError("Invalid value", x)

    def add_enode(self, enode):
        eid = self.hashcons.get(enode)
        if eid is not None:
            return eid
        eid = self.makeset()
        self.enodes[eid] = enode
        self.hashcons[enode] = eid
        return eid

    def add_term(self, term):
        if isinstance(term, tuple):
            if term[0] == "$eid":
                return term[1]
            else:
                name = term[0]
                args = tuple(self.add_term(arg) for arg in term[1:])
                return self.add_enode(Enode(name, args))
        else:
            return self.add_enode(ELit(term))

    def term_view(self, eid, depth):
        assert depth >= 0
        if depth == 0:
            yield ("$eid", eid)
        else:
            for eid1 in self.enum(eid):
                enode = self.enodes[eid1]
                if isinstance(enode, ELit):
                    yield enode.value
                elif isinstance(enode, Enode):
                    for args in itertools.product(
                        *[self.term_view(arg, depth - 1) for arg in enode.args]
                    ):
                        yield (enode.name,) + args

    def check(self):
        for enode, unode in zip(self.enodes, self.unodes):
            assert (unode is None) != (enode is None)
        for eid, unode in enumerate(self.unodes):
            assert unode is None or isinstance(unode, tuple)
        for eid, enode in enumerate(self.enodes):
            if enode is not None:
                assert isinstance(enode, Enode) or isinstance(enode, ELit)
                assert self.hashcons[enode] == eid
    
    # write extract and call after all optimizations/rewrite rules are applied

    def const(self, x):
        eid = self.add_term(("const", x))
        return eid

    def var(self, name):
        eid = self.add_term(("var", name))
        return eid

    def mul(self, x, y):
        eid = self.add_enode(Enode("mul", (x, y)))
        for t in self.term_view(eid, 3):
            if isinstance(t, tuple):
                if (
                    t[0] == "mul"
                    and isinstance(t[1], tuple)
                    and t[1][0] == "const"
                    and isinstance(t[2], tuple)
                    and t[2][0] == "const"
                ):
                    self.union(self.const(t[1][1] * t[2][1]), eid)
                if (
                    t[0] == "mul"
                    and isinstance(t[1], tuple)
                    and t[1][0] == "const"
                    and t[1][1] == 0
                ):
                    self.union(self.const(0), eid)
                if (
                    t[0] == "mul"
                    and isinstance(t[2], tuple)
                    and t[2][0] == "const"
                    and t[2][1] == 0
                ):
                    self.union(self.const(0), eid)
                if (
                    t[0] == "mul"
                    and isinstance(t[1], tuple)
                    and t[1][0] == "const"
                    and t[1][1] == 1
                ):
                    self.union(self.add_term(t[2]), eid)
                if (
                    t[0] == "mul"
                    and isinstance(t[2], tuple)
                    and t[2][0] == "const"
                    and t[2][1] == 1
                ):
                    self.union(self.add_term(t[1]), eid)
                if (
                    t[0] == "mul"
                    and isinstance(t[2], tuple)
                    and t[2][0] == "const"
                    and t[2][1] == 2
                ):
                    self.union(self.lshift(self.add_term(t[1]), self.const(1)), eid)
        return self.find(eid)

    def lshift(self, x, y):
        eid = self.add_enode(Enode("lshift", (x, y)))
        for t in self.term_view(eid, 3):
            if isinstance(t, tuple):
                if (
                    t[0] == "lshift"
                    and isinstance(t[1], tuple)
                    and t[1][0] == "const"
                    and t[1][1] == 0
                ):
                    self.union(self.const(0), eid)
                if (
                    t[0] == "lshift"
                    and isinstance(t[2], tuple)
                    and t[2][0] == "const"
                    and t[2][1] == 0
                ):
                    self.union(self.add_term(t[1]), eid)
                if (
                    t[0] == "lshift"
                    and isinstance(t[1], tuple)
                    and t[1][0] == "const"
                    and isinstance(t[2], tuple)
                    and t[2][0] == "const"
                ):
                    self.union(self.const(t[1][1] << t[2][1]), eid)
        return self.find(eid)

    def div(self, x, y):
        eid = self.add_enode(Enode("div", (x, y)))
        for t in self.term_view(eid, 4):
            if isinstance(t, tuple):
                if (
                    t[0] == "div"
                    and isinstance(t[1], tuple)
                    and t[1][0] == "mul"
                    and isinstance(t[2], tuple)
                    and isinstance(t[1][2], tuple)
                    and t[1][2] == t[2]
                    and t[2][1] != 0
                ):
                    self.union(self.add_term(t[1][1]), eid)
        return self.find(eid)

class TestOptimizeIntBounds(BaseTestBasic):
    
    def test_mul_to_lshift(self):
        ops = """
        [i1, i2]
        i3 = int_mul(i1, 2)
        i4 = int_mul(2, i2)
        i5 = int_mul(i1, 32)
        i6 = int_mul(i1, i2)
        i7 = int_mul(i6, -1)
        jump(i5, i7)
        """
        expected = """
        [i1, i2]
        i3 = int_lshift(i1, 1)
        i4 = int_lshift(i2, 1)
        i5 = int_lshift(i1, 5)
        i6 = int_mul(i1, i2)
        i7 = int_neg(i6)
        jump(i5, i7)
        """
        self.optimize_loop(ops, expected)
