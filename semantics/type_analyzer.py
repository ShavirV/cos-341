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
        #CALL -> NAME ( INPUT )   if type_of(INPUT) is "ok" and type_of(NAME) =/= 'unknown: type_of(CALL) := type_of(NAME)
        name, inp = n.children
        name_type = self._get_name_type(name)
        if inp.type == OK and name_type != UNKNOWN and name_type != ERROR:
            n.type = name_type
        else:
            bad = []
            if inp.type != OK:
                bad.append("INPUT arguments did not resolved to 'ok'")
            if name_type == UNKNOWN:
                bad.append(f"function '{name.value}' is undeclared/untyped")
            elif name_type == ERROR:
                bad.append(f"function '{name.value}' has an unresolved type error")
            self._fail(n, f"Call to '{name.value}' is not well-typed: {'; '.join(bad)}.")
            
    def _r_input_eps(self, n: Node) -> None:
        n.type = OK
    
    def _r_input_cons(self, n: Node) -> None:
        #INPUT -> TERM INPUT
        term, tail = n.children
        if term.type == NUMERIC and tail.type == OK:
            n.type = OK
        else:
            bad = []
            if term.type != NUMERIC:
                bad.append(f"argument TERM is '{term.type}', expected 'numeric'")
            if tail.type != OK:
                bad.append("remaining INPUT did not resolve to 'ok'")
            self._fail(n, f"INPUT list is not well-typed: {'; '.join(bad)}.")
        
    def _r_assign(self, n: Node) -> None:
        #ASSIGN -> NAME = TERM   if type_of(TERM) is "numeric" and type_of(NAME) is "numeric": ASSIGB := "ok"
        name, term = n.children
        name_type = self._get_name_type(name)
        if term.type == NUMERIC and name_type == NUMERIC:
            n.type = OK
        else:
            bad = []
            if name_type != NUMERIC:
                bad.append(f"target '{name.value}' has type '{name_type}', expected 'numeric'")
            if term.type != NUMERIC:
                bad.append(f"right-hand side is '{term.type}', expected 'numeric'")
            self._fail(n, f"Assignment is not well-typed: {'; '.join(bad)}.")

    def _r_term_name(self, n: Node) -> None:
        # TERM -> NAME    if type_of(NAME) is "numeric" then TERM := "numeric"
        name = self._child(n, 0)
        name_type = self._get_name_type(name)
        if name_type == NUMERIC:
            n.type = NUMERIC
        else:
            self._fail(
                n,
                f"Use of '{name.value}' as a numeric TERM requires it to be 'numeric', "
                f"but it is '{name_type}' "
                f"(undeclared variable, or used before declared, or wrong kind of name)."
                if name_type == UNKNOWN else
                f"Use of '{name.value}' as a numeric TERM is invalid: type is '{name_type}', expected 'numeric'.",
            )

    def _r_term_num(self, n: Node) -> None:
        n.type = NUMERIC

    def _r_term_call(self, n: Node) -> None:
        # TERM -> CALL    if type_of(CALL) is "numeric" then TERM := "numeric"
        call = self._child(n, 0)
        if call.type == NUMERIC:
            n.type = NUMERIC
        else:
            reason = {
                PROCEDURE: "it targets a 'void' function, which returns nothing usable as a value",
                ERROR: "the call itself is not well-typed (see the error reported for it above)",
                UNKNOWN: "the called name is undeclared or not yet resolved to a type",
            }.get(call.type, f"the call resolved to type '{call.type}', not 'numeric'")
            self._fail(
                n,
                f"Call used as a numeric TERM must target a 'num' function: {reason}.",
            )

    def _binary_numeric_term(self, n: Node, opname: str) -> None:
        # shared logic for mod/div/add/sub/mul: TERM op ( TERM TERM )
        t1, t2 = n.children
        if t1.type == NUMERIC and t2.type == NUMERIC:
            n.type = NUMERIC
        else:
            bad = []
            if t1.type != NUMERIC:
                bad.append(f"1st operand is '{t1.type}'")
            if t2.type != NUMERIC:
                bad.append(f"2nd operand is '{t2.type}'")
            self._fail(n, f"'{opname}(...)' requires two numeric operands: {', '.join(bad)}.")

    def _r_term_mod(self, n: Node) -> None:
        self._binary_numeric_term(n, "mod")

    def _r_term_div(self, n: Node) -> None:
        self._binary_numeric_term(n, "div")

    def _r_term_add(self, n: Node) -> None:
        self._binary_numeric_term(n, "add")

    def _r_term_sub(self, n: Node) -> None:
        self._binary_numeric_term(n, "sub")

    def _r_term_mul(self, n: Node) -> None:
        self._binary_numeric_term(n, "mul")

    def _r_term_neg(self, n: Node) -> None:
        # TERM -> neg ( TERM )
        t = self._child(n, 0)
        if t.type == NUMERIC:
            n.type = NUMERIC
        else:
            self._fail(n, f"'neg(...)' requires a numeric operand, got '{t.type}'.")

    def _r_branch(self, n: Node) -> None:
        # BRANCH -> if BOOL then { ALGO } else { ALGO }
        bool_, algo1, algo2 = n.children
        if algo1.type == OK and algo2.type == OK and bool_.type == BOOLEAN:
            n.type = OK
        else:
            bad = []
            if bool_.type != BOOLEAN:
                bad.append(f"condition is '{bool_.type}', expected 'boolean'")
            if algo1.type != OK:
                bad.append("'then' branch is not well-typed")
            if algo2.type != OK:
                bad.append("'else' branch is not well-typed")
            self._fail(n, f"if-branch is not well-typed: {'; '.join(bad)}.")

    def _r_bool_not(self, n: Node) -> None:
        b = self._child(n, 0)
        if b.type == BOOLEAN:
            n.type = BOOLEAN
        else:
            self._fail(n, f"'not(...)' requires a boolean operand, got '{b.type}'.")

    def _binary_bool_bool(self, n: Node, opname: str) -> None:
        b1, b2 = n.children
        if b1.type == BOOLEAN and b2.type == BOOLEAN:
            n.type = BOOLEAN
        else:
            bad = []
            if b1.type != BOOLEAN:
                bad.append(f"1st operand is '{b1.type}'")
            if b2.type != BOOLEAN:
                bad.append(f"2nd operand is '{b2.type}'")
            self._fail(n, f"'{opname}(...)' requires two boolean operands: {', '.join(bad)}.")

    def _r_bool_and(self, n: Node) -> None:
        self._binary_bool_bool(n, "and")

    def _r_bool_or(self, n: Node) -> None:
        self._binary_bool_bool(n, "or")

    def _binary_numeric_to_bool(self, n: Node, opname: str) -> None:
        t1, t2 = n.children
        if t1.type == NUMERIC and t2.type == NUMERIC:
            n.type = BOOLEAN
        else:
            bad = []
            if t1.type != NUMERIC:
                bad.append(f"1st operand is '{t1.type}'")
            if t2.type != NUMERIC:
                bad.append(f"2nd operand is '{t2.type}'")
            self._fail(n, f"'{opname}(...)' requires two numeric operands: {', '.join(bad)}.")

    def _r_bool_eq(self, n: Node) -> None:
        self._binary_numeric_to_bool(n, "eq")

    def _r_bool_larger(self, n: Node) -> None:
        self._binary_numeric_to_bool(n, "larger")

    def _r_bool_lesser(self, n: Node) -> None:
        self._binary_numeric_to_bool(n, "lesser")

    def _r_cond(self, n: Node) -> None:
        #COND -> while | until    always "ok"
        n.type = OK

    def _loop_common(self, n: Node) -> None:
        algo, cond, bool_ = n.children
        if algo.type == OK and cond.type == OK and bool_.type == BOOLEAN:
            n.type = OK
        else:
            bad = []
            if cond.type != OK:
                bad.append("COND did not resolve to 'ok'")
            if bool_.type != BOOLEAN:
                bad.append(f"loop condition is '{bool_.type}', expected 'boolean'")
            if algo.type != OK:
                bad.append("loop body ALGO is not well-typed")
            self._fail(n, f"Loop is not well-typed: {'; '.join(bad)}.")

    def _r_loop_pre(self, n: Node) -> None:
        #LOOP -> COND BOOL do { ALGO }
        cond, bool_, algo = n.children
        self._loop_common_ordered(n, cond, bool_, algo)

    def _r_loop_post(self, n: Node) -> None:
        #LOOP -> do { ALGO } COND BOOL
        algo, cond, bool_ = n.children
        self._loop_common_ordered(n, cond, bool_, algo)

    def _loop_common_ordered(self, n: Node, cond: Node, bool_: Node, algo: Node) -> None:
        if algo.type == OK and cond.type == OK and bool_.type == BOOLEAN:
            n.type = OK
        else:
            bad = []
            if cond.type != OK:
                bad.append("COND did not resolve to 'ok'")
            if bool_.type != BOOLEAN:
                bad.append(f"loop condition is '{bool_.type}', expected 'boolean'")
            if algo.type != OK:
                bad.append("loop body ALGO is not well-typed")
            self._fail(n, f"Loop is not well-typed: {'; '.join(bad)}.")

    
    #dispatch table

    _DISPATCH = {}


#populating dispatch table:
TypeAnalyzer._DISPATCH = {
    Kind.SPL_PROG: TypeAnalyzer._r_spl_prog,
    Kind.P: TypeAnalyzer._r_p,
    Kind.V_DECL_EPS: TypeAnalyzer._r_v_decl_eps,
    Kind.V_DECL_CONS: TypeAnalyzer._r_v_decl_cons,
    Kind.F_DECL_EPS: TypeAnalyzer._r_f_decl_eps,
    Kind.F_DECL_CONS: TypeAnalyzer._r_f_decl_cons,
    Kind.F_TYPE_VOID: TypeAnalyzer._r_f_type_void,
    Kind.F_TYPE_NUM: TypeAnalyzer._r_f_type_num,
    Kind.ALGO_EPS: TypeAnalyzer._r_algo_eps,
    Kind.ALGO_CONS: TypeAnalyzer._r_algo_cons,
    Kind.OUTP_TERM: TypeAnalyzer._r_outp_term,
    Kind.OUTP_STRING: TypeAnalyzer._r_outp_string,
    Kind.INSTR_PRINT: TypeAnalyzer._r_instr_print,
    Kind.INSTR_NOP: TypeAnalyzer._r_instr_nop,
    Kind.INSTR_COMMENT: TypeAnalyzer._r_instr_comment,
    Kind.INSTR_ASSIGN: TypeAnalyzer._r_instr_assign,
    Kind.INSTR_BRANCH: TypeAnalyzer._r_instr_branch,
    Kind.INSTR_LOOP: TypeAnalyzer._r_instr_loop,
    Kind.INSTR_CALL: TypeAnalyzer._r_instr_call,
    Kind.CALL: TypeAnalyzer._r_call,
    Kind.INPUT_EPS: TypeAnalyzer._r_input_eps,
    Kind.INPUT_CONS: TypeAnalyzer._r_input_cons,
    Kind.ASSIGN: TypeAnalyzer._r_assign,
    Kind.TERM_NAME: TypeAnalyzer._r_term_name,
    Kind.TERM_NUM: TypeAnalyzer._r_term_num,
    Kind.TERM_CALL: TypeAnalyzer._r_term_call,
    Kind.TERM_MOD: TypeAnalyzer._r_term_mod,
    Kind.TERM_DIV: TypeAnalyzer._r_term_div,
    Kind.TERM_ADD: TypeAnalyzer._r_term_add,
    Kind.TERM_SUB: TypeAnalyzer._r_term_sub,
    Kind.TERM_MUL: TypeAnalyzer._r_term_mul,
    Kind.TERM_NEG: TypeAnalyzer._r_term_neg,
    Kind.BRANCH: TypeAnalyzer._r_branch,
    Kind.BOOL_NOT: TypeAnalyzer._r_bool_not,
    Kind.BOOL_AND: TypeAnalyzer._r_bool_and,
    Kind.BOOL_OR: TypeAnalyzer._r_bool_or,
    Kind.BOOL_EQ: TypeAnalyzer._r_bool_eq,
    Kind.BOOL_LARGER: TypeAnalyzer._r_bool_larger,
    Kind.BOOL_LESSER: TypeAnalyzer._r_bool_lesser,
    Kind.COND_WHILE: TypeAnalyzer._r_cond,
    Kind.COND_UNTIL: TypeAnalyzer._r_cond,
    Kind.LOOP_PRE: TypeAnalyzer._r_loop_pre,
    Kind.LOOP_POST: TypeAnalyzer._r_loop_post,
}
    
