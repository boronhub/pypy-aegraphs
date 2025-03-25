### Dump

- Replace Halide WASM codegen with inferred rules, compare rewrites
	- https://github.com/halide/Halide/blob/main/src/CodeGen_WebAssembly.cpp#L175
- Given phase ordered Halide -> WASM rules, execute rewrites

End goal: compare vector code against Halide -> WASM backend
- Compare performance

- Use Rosette code from Hydride as interpreter? Much slower than Rust but easier to accurately represent semantics
- https://github.com/yblein/rust-wasm/tree/master
- Can it be phase ordered with Cranelift somehow to ensure best patterns for Halide -> WASM -> ARM

Representing global e-graph costs as tensors, do some relational sparse computation

- is strategy for any source -> virtual ISA / bytecode / IR -> real target ISA

From https://github.com/bytecodealliance/wasmtime/issues/6154

> I think that if we could integrate lowering more directly with the sea-of-nodes aegraph representation, that would probably uncover some additional opportunity -- the most direct one being that lowering rules could act as a sort of natural cost function that replaces the ad-hoc one in aegraph extraction. 

TODO: E2E Halide example on WASMTime

Read up on Phase-ordering here - similar approaches but both local and global rewriting: https://dl.acm.org/doi/fullHtml/10.1145/3656019.3689611

Compiling loops to dataflow networks: using EqSat on DF Networks for loop optimizations

- wasmtime tutorial: https://github.com/bytecodealliance/wasmtime/blob/main/docs/WASI-tutorial.md

### EqSat Lowering

- Use MISAAL/MISAAL + Enumo to generate ISLE rewrite rules	
	- ISLE Rewrite Rules: https://github.com/bytecodealliance/wasmtime/blob/main/cranelift/codegen/src/isa/x64/lower.isle
		- try BV rewrites for Enumo with CVC5 bindings at larger depths https://github.com/cvc5/cvc5/blob/main/src/theory/bv/rewrites
	- rewrite systems will never be able to fully compile arbitrary programs because they can’t mint fresh variable: see if aegraphs/e-graphs can be modified with techniques in ISLE rule generator
	- using aegraphs in MISAAL to speed up online time? shouldn't have a lot of the same problems but have to consider globality of rewrites (side conditions for rules generation and application)
	- read up on ISLE: https://cfallin.org/blog/2023/01/20/cranelift-isle/
	- Bible about Rewrite Rules: https://www.philipzucker.com/rewrite_rules/
	- Interesting: can you apply rules as you are enumerating to infer?  
		- https://jrmcclurg.com/papers/pact_2022_paper.pdf (for regex, could it scale to Halide?)
		- see if synthesis techniques outlined here (https://arxiv.org/html/2405.06127v1) are relevant
			- basically AutoLLVM so prob not
	- TensorRight: See if techniques can be used/applied with EqSat

- Using EqSat for generating instruction lowering patterns for both vector and scalar code:
- using modified e-graphs (aegraphs) to infer rewrite rules at larger depths, apply online with swizzles, etc.

### Generating Vectorized Rewrite Rules for JIT using Program Synthesis (CS598 Project?)

- BV level rewrites with Z3/CVC5/Enumo, try with Numba JIT compiler
	- https://pypy.org/posts/2024/07/finding-simple-rewrite-rules-jit-z3.html 
	- https://numba.pydata.org/numba-doc/dev/developer/rewrites.html
	- Look at Numba IR/ PyPy vectors
	- https://github.com/pypy/pypy/blob/main/rpython/doc/jit/vectorization.rst
		- Add AVX as vector backend

	- https://pypy.org/posts/2024/10/jit-peephole-dsl.html


	- can use egglog: https://egglog-python.readthedocs.io/latest/explanation/2023_07_presentation.html 

Use simplified ae-graphs to infer (offline) and apply (online) rewrite rules for PyPy; start with integer ops and move to vectorization 
- novel: (a)e-graphs used in a JIT compiler (could be slower but more optimal - aegraphs might even aid performance as its used in the fastest Rust compiler)
- wins: generate equivalent/extended ruleset automatically, maybe some vectorizing rules

- how to mint fresh vars/constant eval when using egraphs
	- augment with syntheis?
- implement aegraphs in egglog for use with PyPy? seeing wins could be huge, PR at the very least and maybe more substantial work/thesis contribution

- Important blogpost: https://vectorfold.studio/blog/egglog
- Another important post, AEgraph in Python with a very simple JIT: https://www.philipzucker.com/smart_constructor_aegraph/
	- code: https://colab.research.google.com/github/philzook58/philzook58.github.io/blob/master/pynb/2024-09-16-smart_constructor_aegraph.ipynb
- e-graphhs in JIT: https://bernsteinbear.com/blog/whats-in-an-egraph/

- using aegraphs/modified-egraphs both both complex, offline rule inference and online equality-saturation based rewriting with phase ordering
