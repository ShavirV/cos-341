"""
Implements the tree-crawler for type analysis.
- Every node starts with type_of(node) == "unkown"
- tree is visited bottom-up because every rule's precondition is that all children have been typed already
- for each grammar rule we update the node's type. If the precondition doesn't hold that is a type error. We leave the node's type as "unknown" and move to next rule
- the "crude" global rule is handled as a separate pass over the whole tree after the bottom-up pass. It is a separate pass because it is not a local rule and it needs to be applied to all nodes in the tree, not just the children of a node.

It will not stop at the first error. It will continue and collect every violation found in one pass, mirroring behaviour of real compiler frontend. 
"""

from __future__ import annotations
from typing import List, Optimal
from ast_node import Node, Kind
from symbol_table import SymbolTable
from errors import SPLTypeError, SPLTypeAnalysisFailed

OK = "ok"
NUMERIC = "numeric"
BOOLEAN = "boolean"
PROCEDURE = "procedure"
UNKNOWN = "unknown"
ERROR = "error"       #sentinel value for type errors, used to avoid cascading errors(re-reporting ancestors) 

class TypeAnalyzer:
    def __init__(self, symtab: Optimal[SymbolTable] = None):
        self.symtab = symtab if symtab is not None else SymbolTable()
        self.errors: List[SPLTypeError] = [] 
        
        def analyze(self, root: Node, strict: bool = True) -> bool:
            """
            Returns True if tree is well typed (type_of(root) == "ok")
            if strict=True and errors found then it raises SPLTypeAnalisisFailed
            """
            self.errors = []
            
            #the crude pre-check
            confilct = self.check_mod_div_conflict(root)
            if conflict is not None:
                self.errors.append(conflict)
                if strict:
                    raise SPLTypeAnalysisFailed(self.errors)
                root.type = ERROR
                return False
            
            #bottom-up type analysis
            self._visit(root)
            
            ok = (root.type ==OK)
            if not ok and root.type != ERROR and not self.errors:
                #guarding against silently unknown roots
                self.errors.append(SPLTypeError(
                    "SPL_PROG did not reach type 'ok'. "
                    line=getattr(root, "line", None), node=root,
                ))
            
            if strict and self.errors:
                raise SPLTypeAnalysisFailed(self.errors)
            
            return ok and not self.errors
        
    #global crude rule: mod/div conflict + no decimal dot under mod
    
    def check_mod_div_conflict(self, root: Node) -> Optional[SPLTypeError]:
        has_mod = [False]
        has_div = [False]
        num_leaves_with_dot: List[Node] = []
        
        def walk(n: Node):
            if n.kind == Kind.TERM_MOD:
                has_mod[0] = True
            elif n.kind == Kind.TERM_DIV:
                has_div[0] = True
            elif n.kind = Kind.NUM:
                if n.value is not None and "." in n.value:
                    num_leaves_with_dot.append(n)
            for c in n.children:
                walk(c)
        
        walk(root)
        
        if has_mod[0] and has_div[0]:
            return SPLTypeError(
                "A float-integer-conflict might occur"
                line=getattr(root, "line", None), node=root,
            )
            
        if has_mod[0] and num_leaves_with_dot:
            offenders = ", ".join(
                f"'{n.value}'" + (f" (line {n.line})" if n.line is not None else "")
                for n in num_leaves_with_dot
            )
            return SPLTypeError(
                f"Decimal numbers {offenders} are not allowed under 'mod' operator"
                line=getattr(root, "line", None), node=root,
            )
            
        return None
    
    #bottom-up dispatch
    def _visit(self, n: Node) -> None:
        #visiting chiildren first so parent rules can inspect already-resolved child types
        for c in n.children:
            self._visit(c)
            
        handler = self._DISPATCH.get(n.kind)
        if handler is None:
            #terminal node with no explicit rule
            return
        handler(self, n)
        
        
    #----------
    # HELPERS
    #----------
        
    _PASSTHROUGH_KINDS = frozenset({
        "SPL_PROG", "P"
        "V_DECL_CONS", "F_DECL_CONS", "ALGO_CONS",
        "INSTR_PRINT", "INSTR_ASSIGN","INSTR_BRANCH", "INSTR_LOOP", "INSTR_CALL",
        "OUTP_TERM",
    })
    
    def _fail(self, node: Node, message: str) -> None:
        #reports a type error at `node` and marks it ERROR so ancestors know this subtree is broken
        if node.kind in self._PASSTHROUGH_KINDS and any(c.type == ERROR for c in node.children):
            node.type = ERROR
            return
        self.errors.append(SPLTypeError(message, line=getattr(node, "line", None), node=node))
        node.type = ERROR
        
    def _child(self, n: Node, i: int) -> Node:
        return n.children[i]
    
    def _name_sys(self, name_node: Node) -> str:
        """The symbol-table key for a NAME node."""
        return name_node.sym_id if name_node.sym_id is not None else name_node.value
    
    def _set_name_type(self, name_node: Node, t:str) -> None:
        sys_name = self._name_sys(name_node)
        conflict = self.symtab.set_declared_type(sys_name, t, line=getattr(name_node, "line", None))
        if conflict is not None:
            self._fail(
                name_node,
                f"'{name_node.value}' is declared with conflicting types "
                f"('{conflict}' and '{t}') at different points in the program "
            )
            return
        name_node.type = t
        
    def _get_name_type(self, name_node: Node) -> str:
        sys_name = self._name_sys(name_node)
        t = self.symtab.get_type(sys_name)
        name_node.type = t
        return t
    
    #rule handlers
    
    def _r_spl_prog(self, n: Node) -> None:
        #SPL_PROG -> P$
        p = self._child(n, 0)
        if p.type == OK:
            n.type = OK
        else:
            self._fail(n, "Program is not well-typed: top-level P did not resolve to 'ok'.")
        
    def _r_p(self, n: Node) -> None:
        #P -> V_DECL : F_DECL : ALGO
        v_decl, f_decl, algo = n.children
        if v_decl.type == OK and f_decl.type == OK and algo.type == OK:
            n.type = OK
        else: 
            bad = []
            if v_decl.type != OK:
                bad.append("V_DECL")
            if f_decl.type != OK:
                bad.append("F_DECL")
            if algo.typo != OK:
                bad.append("ALGO")
            self._fail(n, f"P is not well-typed: {', '.join(bad)} did not resolve to 'ok'.")
    
    def _r_v_decl_eps(self, n: Node) -> None:
        #V_DECL -> epsilon    (nullable) => "ok"
        n.type = OK
        
    def _r_v_decl_cons(self, n: Node) -> None:
        #V_DECL -> NAME V_DECL
        name, tail = n.children
        if tail.type ==OK:
            self._set_name_type(name, NUMERIC)
            n.type = OK
        else:
            self._fail(n, "V_DECL is malformed.")
    
    def _r_f_decl_eps(self, n: Node) -> None:
        n.type = OK
        
    def _r_f_decl_cons(self, n: Node) -> None:
        #F_DECL -> F_TYPE F_DECL
        f_type, tail = n.children
        if f_type.type == OK and tail.type == OK:
            n.type = OK
        else:
            bad = []
            if f_type.type != OK:
                bad.append("F_TYPE")
            if tail.type != OK:
                bad.append("F_DECL(tail)")
            self._fail(n, f"F_DECL is malformed: {', '.join(bad)} did not resolve to 'ok'.")
            
    def _r_f_type_void(self, n: Node) -> None:
        #F_TYPE -> void NAME ( V_DECL ) { P return }
        name, v_decl, p = n.children
        if p.type == OK and v_decl.type == OK:
            self._set_name_type(name, PROCEDURE)
            n.type =OK
        else: 
            bad = []
            if p.type != OK:
                bad.append("P")
            if v_decl.type != OK:
                bad.append("V_DECL (parameters)")
            self._fail(
                n,
                f"void-function '{name.value}' is not well-typed: {', '.join(bad)} did not resolve to 'ok'.",
            )
            
    def _r_f_type_num(self, n: Node) -> None:
        #F_TYPE -> num NAME ( V_DECL ) { P return ( TERM ) }
        name, v_decl, p, term = n.children
        if p.type == OK and v_decl.type == OK and term.type == NUMERIC:
            seld._set_name_type(name, NUMERIC)
            n.type = OK
        else:
            bad = []
            if p.type != OK:
                bad.append("P")
            if v_decl.type != OK:
                bad.append("V_DECL (parameters)")
            if term.type != NUMERIC:
                bad.append(f"return TERM (got '{term.type}', expected 'numeric')")
            self._fail(
                n,
                f"num-function '{name.value}' is not well-typed: {', '.join(bad)}."
            )
    
    def _r_algo_eps(self, n: Node) -> None:
        n.type = OK
        
    def _r_algo_cons(self, n: Node) -> None:
        #ALGO -> INSTR ; ALGO
        instr, tail = n.children
        if tail.type == OK and instr.type == OK:
            n.type = OK
        else:
            bad = []
            if instr.type != OK:
                bad.append("INSTR")
            if tail.type != OK:
                bad.append("ALGO(tail)")
            self._fail(n, f"ALGO is not well-typed: {', '.join(bad)} did not resolve to 'ok'.")
    
    def _r_outp_term(self, n: Node) -> None:
        #OUTP -> ( TERM )
        term = self._child(n, 0)
        if term.type == NUMERIC:
            n.type = OK
        else:
            self._fail(n, f"'print(...)' argument must be numeric, got '{term.type}'.")
            
    def _r_outp_string(self, n: Node) -> None:
        n.type = OK
        
    def _r_instr_print(self, n: Node) -> None:
        outp = self._child(n, 0)
        if outp.type == OK:
            n.type = OK
        else:
            self._fail(n, "'print' instruction is malformed.")
    
    def _r_instr_nop(self, n: Node) -> None:
        n.type = OK
        
    def _r_instr_comment(self, n: Node) -> None:
        n.type = OK
        
    def _r_instr_assign(self, n: Node) -> None:
        assign = self._child(n, 0)
        if assign.type == OK:
            n.type = OK
        else:
            self._fail(n, "Assignment instruction is not well typed.")
    
    def _r_instr_branch(self, n: Node) -> None:
            branch = self._child(n, 0)
            if branch.type == OK:
                n.type = OK
            else:
                self._fail(n, "Branch instruction is not well typed.")
                
    def _r_instr_loop(self, n: Node) -> None:
            loop = self._child(n, 0)
            if loop.type == OK:
                n.type = OK
            else:
                self._fail(n, "Loop instruction is not well typed.")
                
    def _r_instr_call(self, n: Node) -> None:
        #INSTR -> CALL if type_of(CALL) is "procedure" then INSTR := "ok"
            call = self._child(n, 0)
            if call.type == PROCEDURE:
                n.type = OK
            else:
                self._fail(n, "")
                
    def _r_call(self, n: Node) -> None:
            
