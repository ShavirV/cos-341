"""
Phase 2a: semantic analysis of scopes and names.

Walks the abstract syntax tree (semantics.ast_nodes.Node) once, top-down,
and does three things:

1. CHECKS the scope rules of the SPL 
2. RENAMES every user-defined NAME node with a unique system-generated name
   ("sys1", "sys2", ...) such that two NAME nodes carry the same new name
   if and only if they denote the same computational entity
3. RECORDS every declaration (new name, original name, kind, scope level,
   line) in the SymbolTable, for the type analyzer and the code generator

Scope model 
* The top-level P is Scope Level 0.
* A function declared in the F_DECL of a P at level l has its parameters and
  its body P at level l+1.
* Parameters and the body's own V_DECL live at the SAME level: they form one
  "variable scope" (hence a local may not mask a parameter).

Variables
  - A use of x (assignment target, TERM, ...) must find a declaration in the
    variable scope of an ANCESTOR (or the same) P. The nearest one wins.
    Declarations in a "sideways" function (Announcement #21) are invisible.
  - No name may be declared twice at the same level.

Functions
  - Strictly hierarchic: a call in the ALGO of a P (and in the return TERM of
    the function whose body that P is) may only target a function declared in
    the F_DECL of THAT SAME P. No recursion, no sibling or outer calls.
  - Function names must be unique within one F_DECL (no overloading).

Variables and functions live in separate namespaces, so a variable and a
function may share a spelling. They still receive different internal names.

After this pass NAME.sym_id holds the new internal name, while NAME.value
keeps the original spelling so that later error messages stay readable.

Like the type analyzer, ALL errors are collected rather than stopping at the
first one. The walk is iterative: ALGO / V_DECL / F_DECL nest once per list
element, so a recursive walk would hit Python's recursion limit on long
programs.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from semantics.ast_nodes import Node, Kind
from semantics.symbol_table import SymbolTable
from semantics.errors import SPLScopeError, SPLScopeAnalysisFailed

VAR = "var"
FUNC = "func"


class _Frame:
    """The names visible in one P (one scope level)."""

    __slots__ = ("level", "parent", "vars", "funcs", "func_name")

    def __init__(self, level: int, parent: Optional["_Frame"], func_name: Optional[str] = None):
        self.level = level
        self.parent = parent
        self.vars: Dict[str, str] = {}    # original name -> new name (params + locals)
        self.funcs: Dict[str, str] = {}   # original name -> new name (this P's F_DECL)
        self.func_name = func_name        # name of the function whose body this is (None at level 0)


class ScopeAnalyzer:
    def __init__(self, symtab: Optional[SymbolTable] = None, prefix: str = "sys"):
        self.symtab = symtab if symtab is not None else SymbolTable()
        self.errors: List[SPLScopeError] = []
        self._prefix = prefix
        self._counter = 0

    # ------ API

    def analyze(self, root: Node, strict: bool = False) -> bool:
        """
        Returns True if the program obeys all scope rules.
        If strict=True and errors were found, raises SPLScopeAnalysisFailed.
        Renaming is performed even for erroneous programs (names that could be
        resolved are renamed, unresolvable ones keep their spelling).
        """
        self.errors = []
        self._counter = 0
        p = root.children[0] if root.kind == Kind.SPL_PROG else root
        self._scope_p(p, level=0, parent=None, func_name=None, params=None, ret_term=None)
        self.errors.sort(key=lambda e: (e.line is None, e.line or 0))   # stable: keeps walk order per line
        if strict and self.errors:
            raise SPLScopeAnalysisFailed(self.errors)
        return not self.errors

    # -- helpers

    def _new_name(self) -> str:
        self._counter += 1
        return f"{self._prefix}{self._counter}"

    def _err(self, msg: str, node: Optional[Node]) -> None:
        self.errors.append(SPLScopeError(msg, line=getattr(node, "line", None), node=node))

    @staticmethod
    def _list_items(n: Node, cons_kind: str) -> List[Node]:
        """Flatten a right-recursive list (V_DECL / F_DECL / ALGO / INPUT) iteratively."""
        out = []
        while n.kind == cons_kind:
            out.append(n.children[0])
            n = n.children[1]
        return out

    def _declare_var(self, name_node: Node, frame: _Frame, origin: str,
                     param_names: Optional[set] = None) -> None:
        orig = name_node.value
        if orig in frame.vars:
            if param_names is not None and orig in param_names and origin == "local":
                self._err(f"local variable '{orig}' masks the parameter '{orig}' of "
                          f"function '{frame.func_name}' (scope level {frame.level}).", name_node)
            else:
                what = "parameter" if origin == "param" else "variable"
                self._err(f"{what} '{orig}' is declared more than once at scope level "
                          f"{frame.level}.", name_node)
            # still tie this node to the first declaration so later uses stay consistent
            name_node.sym_id = frame.vars[orig]
            return
        new = self._new_name()
        frame.vars[orig] = new
        name_node.sym_id = new
        self.symtab.declare(new, "unknown", kind=VAR, line=name_node.line,
                            orig_name=orig, scope_level=frame.level)

    def _declare_func(self, name_node: Node, frame: _Frame) -> None:
        orig = name_node.value
        if orig in frame.funcs:
            self._err(f"function '{orig}' is declared more than once in the F_DECL of "
                      f"scope level {frame.level} (function names must be unique; "
                      f"overloading is not allowed).", name_node)
            name_node.sym_id = frame.funcs[orig]
            return
        new = self._new_name()
        frame.funcs[orig] = new
        name_node.sym_id = new
        # as in Fig.1 / Announcement #21, a function "is defined at" the level of its
        # own header and body, i.e. one deeper than the F_DECL that lists it
        self.symtab.declare(new, "unknown", kind=FUNC, line=name_node.line,
                            orig_name=orig, scope_level=frame.level + 1)

    def _resolve_var(self, name_node: Node, frame: _Frame) -> None:
        orig = name_node.value
        f: Optional[_Frame] = frame
        while f is not None:                       # ancestors only, nearest first
            if orig in f.vars:
                name_node.sym_id = f.vars[orig]
                return
            f = f.parent
        if orig in self._all_funcs_hint(frame):
            self._err(f"'{orig}' is used as a variable but is only declared as a function.",
                      name_node)
        else:
            self._err(f"variable '{orig}' is used but has no declaration in any enclosing "
                      f"scope.", name_node)

    def _resolve_func(self, name_node: Node, frame: _Frame) -> None:
        orig = name_node.value
        if orig in frame.funcs:                    # same P's F_DECL only
            name_node.sym_id = frame.funcs[orig]
            return
        # produce a helpful diagnosis, but it is an error in every case
        f = frame.parent
        while f is not None:
            if orig in f.funcs:
                self._err(f"function '{orig}' is called at scope level {frame.level}, but it is "
                          f"declared in the F_DECL of the outer scope level {f.level}. Calls must "
                          f"target a function declared in the F_DECL of the same block "
                          f"(no recursion, no calls to outer or sibling functions).", name_node)
                return
            f = f.parent
        if orig in frame.vars:
            self._err(f"'{orig}' is called as a function but is only declared as a variable.",
                      name_node)
        else:
            self._err(f"function '{orig}' is called but has no declaration in the F_DECL of "
                      f"the same block (scope level {frame.level}).", name_node)

    @staticmethod
    def _all_funcs_hint(frame: _Frame) -> set:
        s = set()
        f: Optional[_Frame] = frame
        while f is not None:
            s.update(f.funcs)
            f = f.parent
        return s

    #  the walk

    def _scope_p(self, p: Node, level: int, parent: Optional[_Frame],
                 func_name: Optional[str], params: Optional[Node], ret_term: Optional[Node]) -> None:
        """
        Process one P node (one scope level). Uses an explicit work stack so that
        nested function bodies do not consume Python call-stack depth.
        """
        stack: List[Tuple] = [("P", p, level, parent, func_name, params, ret_term)]
        while stack:
            item = stack.pop()
            if item[0] == "P":
                _, p, level, parent, func_name, params, ret_term = item
                frame = _Frame(level, parent, func_name)
                v_decl, f_decl, algo = p.children

                # 1) variables: parameters first, then the body's locals (same level)
                param_names = set()
                if params is not None:
                    for nm in self._list_items(params, Kind.V_DECL_CONS):
                        param_names.add(nm.value)
                        self._declare_var(nm, frame, "param")
                for nm in self._list_items(v_decl, Kind.V_DECL_CONS):
                    self._declare_var(nm, frame, "local", param_names)

                # 2) functions listed in this P's F_DECL
                funcs = self._list_items(f_decl, Kind.F_DECL_CONS)
                for ft in funcs:
                    self._declare_func(ft.children[0], frame)

                # 3) uses inside this P's own ALGO (and the function's return TERM)
                self._walk_uses(algo, frame)
                if ret_term is not None:
                    self._walk_uses(ret_term, frame)

                # 4) descend into the sub-functions (one level deeper)
                for ft in reversed(funcs):
                    f_params, f_body = ft.children[1], ft.children[2]
                    f_ret = ft.children[3] if ft.kind == Kind.F_TYPE_NUM else None
                    stack.append(("P", f_body, level + 1, frame, ft.children[0].value,
                                  f_params, f_ret))

    def _walk_uses(self, root: Node, frame: _Frame) -> None:
        """Resolve every NAME *use* below `root` (an ALGO or a return TERM).
        Never enters function declarations: ALGO and TERM contain none."""
        stack = [root]
        while stack:
            n = stack.pop()
            k = n.kind
            if k == Kind.CALL:
                self._resolve_func(n.children[0], frame)
                stack.append(n.children[1])
                continue
            if k == Kind.ASSIGN or k == Kind.TERM_NAME:
                self._resolve_var(n.children[0], frame)
                if k == Kind.ASSIGN:
                    stack.append(n.children[1])
                continue
            stack.extend(reversed(n.children))
