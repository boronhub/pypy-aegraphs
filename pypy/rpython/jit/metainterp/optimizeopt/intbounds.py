import sys
from rpython.jit.metainterp.history import ConstInt
from rpython.jit.metainterp.optimize import InvalidLoop
from rpython.jit.metainterp.optimizeopt.intutils import IntBound
from rpython.jit.metainterp.optimizeopt.optimizer import (Optimization, CONST_1,
    CONST_0)
from rpython.jit.metainterp.optimizeopt.util import (
    make_dispatcher_method, have_dispatcher_method, get_box_replacement)
from rpython.jit.metainterp.optimizeopt.info import getptrinfo
from rpython.jit.metainterp.resoperation import rop
from rpython.jit.metainterp.optimizeopt import vstring
from rpython.jit.metainterp.optimizeopt import autogenintrules
from rpython.jit.codewriter.effectinfo import EffectInfo
from rpython.rlib.rarithmetic import intmask
from rpython.rlib.debug import debug_print
from rpython.rlib import objectmodel
import itertools

import sys
from rpython.jit.metainterp.history import ConstInt
from rpython.jit.metainterp.optimizeopt.util import (
    get_box_replacement)
from rpython.jit.metainterp.resoperation import rop

from rpython.rlib.rarithmetic import LONG_BIT, r_uint, intmask, ovfcheck, uint_mul_high, highest_bit
MAXINT = sys.maxint
MININT = -sys.maxint - 1


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

    def const(self, x):
        eid = self.add_term(("const", x))
        return eid

    def var(self, name):
        eid = self.add_term(("var", name))
        return eid

    def mul(self, x, y):
        eid = self.add_enode(Enode("mul", (x, y)))
        for t in self.term_view(eid, 3):
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "mul" and \
            isinstance(t[1], tuple) and len(t[1]) == 2 and t[1][0] == "const" and \
            isinstance(t[2], tuple) and len(t[2]) == 2 and t[2][0] == "const":
                x_val = t[1][1]
                y_val = t[2][1]
                self.union(self.const(x_val * y_val), eid)
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "mul":
                if (isinstance(t[1], tuple) and len(t[1]) == 2 and t[1][0] == "const" and t[1][1] == 0):
                    b = t[2]
                    self.union(self.const(0), eid)
                elif (isinstance(t[2], tuple) and len(t[2]) == 2 and t[2][0] == "const" and t[2][1] == 0):
                    b = t[1]
                    self.union(self.const(0), eid)
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "mul":
                if (isinstance(t[1], tuple) and len(t[1]) == 2 and t[1][0] == "const" and t[1][1] == 1):
                    b = t[2]
                    self.union(self.add_term(b), eid)
                elif (isinstance(t[2], tuple) and len(t[2]) == 2 and t[2][0] == "const" and t[2][1] == 1):
                    b = t[1]
                    self.union(self.add_term(b), eid)
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "mul":
                if (isinstance(t[1], tuple) and len(t[1]) == 2 and t[1][0] == "const" and t[1][1] == -1):
                    b = t[2]
                    self.union(self.neg(self.add_term(b)), eid)
                elif (isinstance(t[2], tuple) and len(t[2]) == 2 and t[2][0] == "const" and t[2][1] == -1):
                    b = t[1]
                    self.union(self.neg(self.add_term(b)), eid)
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "mul" and \
                isinstance(t[2], tuple) and len(t[2]) == 2 and t[2][0] == "const" and (t[2][1] & intmask(r_uint(t[2][1]) - r_uint(1)) == 0) :
                a = t[1]
                self.union(self.lshift(self.add_term(a), self.const(highest_bit(t[2][1]))), eid)
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "mul" and \
                isinstance(t[2], tuple) and len(t[2]) == 2 and t[1][0] == "const" and (t[1][1] & intmask(r_uint(t[1][1]) - r_uint(1)) == 0) :
                a = t[2]
                self.union(self.lshift(self.add_term(a), self.const(highest_bit(t[1][1]))), eid) 
        return self.find(eid)

    def lshift(self, x, y):
        eid = self.add_enode(Enode("lshift", (x, y)))
        for t in self.term_view(eid, 3):
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "lshift" and \
            isinstance(t[1], tuple) and len(t[1]) == 2 and t[1][0] == "const" and t[1][1] == 0:
                b = t[2]
                self.union(self.const(0), eid)
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "lshift" and \
                isinstance(t[2], tuple) and len(t[2]) == 2 and t[2][0] == "const" and t[2][1] == 0:
                a = t[1]
                self.union(self.add_term(a), eid)
            if isinstance(t, tuple) and len(t) == 3 and t[0] == "lshift" and \
                isinstance(t[1], tuple) and len(t[1]) == 2 and t[1][0] == "const" and \
                isinstance(t[2], tuple) and len(t[2]) == 2 and t[2][0] == "const":
                x_val = t[1][1]
                y_val = t[2][1]
                self.union(self.const(x_val << y_val), eid)
        return self.find(eid)
    
    def neg(self, x):
        eid = self.add_enode(Enode("neg", (x, )))
        return self.find(eid)
        

    def div(self, x, y):
        eid = self.add_enode(Enode("div", (x, y)))
        for t in self.term_view(eid, 4):
            if isinstance(t, tuple) and len(t) == 4 and t[0] == "div" and \
            isinstance(t[1], tuple) and len(t[1]) == 3 and t[1][0] == "mul":
                a = t[1][1]
                b = t[1][2]
                b1 = t[2]
                if b == b1 and b != 0:
                    self.union(self.add_term(a), eid)
        return self.find(eid)

def get_integer_min(is_unsigned, byte_size):
    if is_unsigned:
        return 0
    else:
        return -(1 << ((byte_size << 3) - 1))


def get_integer_max(is_unsigned, byte_size):
    if is_unsigned:
        return (1 << (byte_size << 3)) - 1
    else:
        return (1 << ((byte_size << 3) - 1)) - 1


# add all program exprs to aegraph and extract in separate function?

class OptIntBounds(Optimization):
    """Keeps track of the bounds placed on integers by guards and remove
       redundant guards"""
    
    def __init__(self):
        self.aegraph = AEGraph()

    def propagate_forward(self, op):
        return dispatch_opt(self, op)

    def propagate_bounds_backward(self, box):
        # FIXME: This takes care of the instruction where box is the result
        #        but the bounds produced by all instructions where box is
        #        an argument might also be tighten
        b = self.getintbound(box)
        if b.is_constant():
            self.make_constant_int(box, b.get_constant_int())

        box1 = self.optimizer.as_operation(box)
        if box1 is not None:
            dispatch_bounds_ops(self, box1)

    def _postprocess_guard_true_false_value(self, op):
        if op.getarg(0).type == 'i':
            self.propagate_bounds_backward(op.getarg(0))

    postprocess_GUARD_TRUE = _postprocess_guard_true_false_value
    postprocess_GUARD_FALSE = _postprocess_guard_true_false_value
    postprocess_GUARD_VALUE = _postprocess_guard_true_false_value

    def _eq(self, box1, bound1, box2, bound2):
        if box1 is box2: return True
        if bound1.is_constant() and bound2.is_constant() and bound1.lower == bound2.lower: return True
        return False
    _all_rules_fired = []
    _rule_names_int_mul = ['mul_zero', 'mul_one', 'mul_minus_one', 'mul_pow2_const', 'mul_lshift', 'aegraph_mul_const']
    _rule_fired_int_mul = [0] * 6
    _all_rules_fired.append(('int_mul', _rule_names_int_mul, _rule_fired_int_mul))
    var_counter = 0
    
    def aegraph_optimize_INT_MUL(self, op):
        arg_0 = get_box_replacement(op.getarg(0))
        b_arg_0 = self.getintbound(arg_0)
        arg_1 = get_box_replacement(op.getarg(1))
        b_arg_1 = self.getintbound(arg_1)
        
        if b_arg_0.is_constant():
            C_arg_0 = b_arg_0.get_constant_int()
            C_arg_0_aegraph = self.aegraph.const(C_arg_0)
        else:
            C_arg_0_aegraph = self.aegraph.var("var_{0}".format(self.var_counter))
            self.var_counter += 1

        if b_arg_1.is_constant():
                C_arg_1 = b_arg_1.get_constant_int()
                C_arg_1_aegraph = self.aegraph.const(C_arg_1)
        else:
            C_arg_1_aegraph = self.aegraph.var("var_{0}".format(self.var_counter))
            self.var_counter += 1
        
        mul_op = self.aegraph.mul(C_arg_0_aegraph, C_arg_1_aegraph)
        #print("AEGraph after MUL operation: ", self.aegraph)
        extracted = list(self.aegraph.term_view(self.aegraph.find(mul_op), 10))[0]
        if extracted[0] == "lshift":  
            if b_arg_0.is_constant():
                newop = self.replace_op_with(op, rop.INT_LSHIFT, args=[arg_1, ConstInt(extracted[2][1])])
            elif b_arg_1.is_constant():
                newop = self.replace_op_with(op, rop.INT_LSHIFT, args=[arg_0, ConstInt(extracted[2][1])])
            self.optimizer.send_extra_operation(newop)
            return
        if extracted[0] == "const":
            const_val = list(self.aegraph.term_view(self.aegraph.find(mul_op), 10))[0][1]
            self.make_constant_int(op, const_val)
            return
        if extracted[0] == "neg":
            if b_arg_0.is_constant() and b_arg_0.get_constant_int() == -1:
                newop = self.replace_op_with(op, rop.INT_NEG, args=[arg_1])
            elif b_arg_1.is_constant():
                newop = self.replace_op_with(op, rop.INT_NEG, args=[arg_0])

            self.optimizer.send_extra_operation(newop)
            return

        self._rule_fired_int_mul[5] += 1
        print("\n\n\n")
        return self.emit(op)
               
    def postprocess_INT_MUL(self, op):
        b1 = self.getintbound(op.getarg(0))
        b2 = self.getintbound(op.getarg(1))
        r = self.getintbound(op)
        b = b1.mul_bound(b2)
        r.intersect(b)

    def postprocess_INT_LSHIFT(self, op):
        arg0 = get_box_replacement(op.getarg(0))
        b1 = self.getintbound(arg0)
        arg1 = get_box_replacement(op.getarg(1))
        b2 = self.getintbound(arg1)
        r = self.getintbound(op)
        b = b1.lshift_bound(b2)
        r.intersect(b)
        if b1.lshift_bound_cannot_overflow(b2):
            # Synthesize the reverse op for optimize_default to reuse.
            # This is important because overflow checking for lshift is done
            # like this (in ll_int_lshift_ovf in rint.py):
            #  result = x << y
            #  if (result >> y) != x:
            #      raise OverflowError("x<<y loosing bits or changing sign")
            self.pure_from_args2(rop.INT_RSHIFT,
                                 op, arg1, arg0)

    def optimize_GUARD_NO_OVERFLOW(self, op):
        lastop = self.last_emitted_operation
        if lastop is not None:
            opnum = lastop.getopnum()
            args = lastop.getarglist()
            result = lastop
            # If the INT_xxx_OVF was replaced with INT_xxx or removed
            # completely, then we can kill the GUARD_NO_OVERFLOW.
            if (opnum != rop.INT_ADD_OVF and
                opnum != rop.INT_SUB_OVF and
                opnum != rop.INT_MUL_OVF):
                return
            # Else, synthesize the non overflowing op for optimize_default to
            # reuse, as well as the reverse op
            elif opnum == rop.INT_ADD_OVF:
                self.pure_from_args2(rop.INT_SUB, result, args[1], args[0])
                self.pure_from_args2(rop.INT_SUB, result, args[0], args[1])
            elif opnum == rop.INT_SUB_OVF:
                self.pure_from_args2(rop.INT_ADD, result, args[1], args[0])
                self.pure_from_args2(rop.INT_SUB, args[0], result, args[1])
            return self.emit(op)

    def optimize_GUARD_OVERFLOW(self, op):
        # If INT_xxx_OVF was replaced by INT_xxx, *but* we still see
        # GUARD_OVERFLOW, then the loop is invalid.
        lastop = self.last_emitted_operation
        if lastop is None:
            return # e.g. beginning of the loop
        opnum = lastop.getopnum()
        if opnum not in (rop.INT_ADD_OVF, rop.INT_SUB_OVF, rop.INT_MUL_OVF):
            raise InvalidLoop('An INT_xxx_OVF was proven not to overflow but' +
                              'guarded with GUARD_OVERFLOW')

        return self.emit(op)

    def propagate_bounds_INT_MUL(self, op):
        b1 = self.getintbound(op.getarg(0))
        b2 = self.getintbound(op.getarg(1))
        if op.opnum != rop.INT_MUL_OVF and not b1.mul_bound_cannot_overflow(b2):
            # we can only do divide if the operation didn't overflow
            return
        r = self.getintbound(op)
        b = r.py_div_bound(b2)
        if b1.intersect(b):
            self.propagate_bounds_backward(op.getarg(0))
        b = r.py_div_bound(b1)
        if b2.intersect(b):
            self.propagate_bounds_backward(op.getarg(1))

    def propagate_bounds_INT_LSHIFT(self, op):
        b1 = self.getintbound(op.getarg(0))
        b2 = self.getintbound(op.getarg(1))
        if not b1.lshift_bound_cannot_overflow(b2):
            return
        r = self.getintbound(op)
        b = r.lshift_bound_backwards(b2)
        if b1.intersect(b):
            self.propagate_bounds_backward(op.getarg(0))

    #objectmodel.import_from_mixin(autogenintrules.OptIntAutoGenerated)

#dispatch_opt = make_dispatcher_method(OptIntBounds, 'optimize_', default=OptIntBounds.emit)

dispatch_opt = make_dispatcher_method(OptIntBounds, 'aegraph_optimize_',
                                      default=OptIntBounds.emit)
dispatch_bounds_ops = make_dispatcher_method(OptIntBounds, 'propagate_bounds_')
OptIntBounds.propagate_postprocess = make_dispatcher_method(OptIntBounds, 'postprocess_')
OptIntBounds.have_postprocess_op = have_dispatcher_method(OptIntBounds, 'postprocess_')


class IntegerAnalysisLogger(object):
    def __init__(self, optimizer):
        from rpython.jit.metainterp.logger import LogOperations

        self.optimizer = optimizer
        self.log_operations = LogOperations(
                    optimizer.metainterp_sd, False, None)
        self.last_printed_repr_memo = {}

    def log_op(self, op):
        # print the intbound of all arguments (they might have changed since
        # they were produced)
        for i in range(op.numargs()):
            arg = get_box_replacement(op.getarg(i))
            if arg.type != 'i' or arg.is_constant():
                continue
            b = arg.get_forwarded()
            if not isinstance(b, IntBound) or b.is_unbounded():
                continue
            argop = self.optimizer.as_operation(arg)
            if argop is not None and rop.returns_bool_result(arg.opnum) and b.is_bool():
                continue
            r = b.__repr__()
            if self.last_printed_repr_memo.get(arg, '') == r:
                continue
            self.last_printed_repr_memo[arg] = r
            debug_print("# %s: %s   %s" % (
                self.log_operations.repr_of_arg(arg), b.__str__(), r))
        debug_print(self.log_operations.repr_of_resop(op))

    def log_result(self, op):
        if op.type == 'i':
            b = op.get_forwarded()
            if not isinstance(b, IntBound):
                return
            if rop.returns_bool_result(op.opnum):
                return
            # print the result bound too
            r = b.__repr__()
            debug_print("# %s -> %s   %s" % (
                self.log_operations.repr_of_arg(op), b.__str__(), r))
            self.last_printed_repr_memo[op] = r

    def log_inputargs(self, inputargs):
        args = ", ".join([self.log_operations.repr_of_arg(arg) for arg in inputargs])
        debug_print('[' + args + ']')

def print_rewrite_rule_statistics():
    from rpython.rlib.debug import debug_start, debug_stop, have_debug_prints
    debug_start("jit-intbounds-stats")
    if have_debug_prints():
        for opname, names, counts in OptIntBounds._all_rules_fired:
            debug_print(opname)
            for index in range(len(names)):
                debug_print("    " + names[index], counts[index])
    debug_stop("jit-intbounds-stats")
