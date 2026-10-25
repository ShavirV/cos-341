from __future__ import annotations
from typing import List, Optional

from semantics.ast_nodes import Node, Kind
from semantics.symbol_table import SymbolTable
from semantics.errors import SPLTypeError, SPLTypeAnalysisFailed

OK = "ok"
NUMERIC = "numeric"
BOOLEAN = "boolean"
PROCEDURE = "procedure"
UNKNOWN = "unknown"
ERROR = "error"       #sentinel value for type errors, used to avoid cascading errors(re-reporting ancestors)

# number representation for the whole program, decided by the crude-rule scan
INT = "int"
FLOAT = "float"

# exact wording required by the 2b spec sheet
FLOAT_INT_CONFLICT_MSG = "A float-integer-conflict might perhaps be possible"

class TypeAnalyzer:
    def __init__(self, symtab: Optional[SymbolTable] = None):
        self.symtab = symtab if symtab is not None else SymbolTable()
        self.errors: List[SPLTypeError] = []
        # "int" or "float" once analyze() has run; phase 3a declares its temps with this
        self.number_type: Optional[str] = None
        self._arity = {}      # function sys-name -> number of parameters

    def analyze(self, root: Node, strict: bool = True) -> bool:
        """
        Returns True if tree is well typed (type_of(root) == "ok")
        if strict=True and errors found then it raises SPLTypeAnalisisFailed
        """
        self.errors = []
        self.number_type = None
        self._arity = {}

        #pass 1: the crude pre-check (also decides int vs float)
        conflict = self.check_mod_div_conflict(root)
        if conflict is not None:
            self.errors.append(conflict)
            if strict:
                raise SPLTypeAnalysisFailed(self.errors)
            root.type = ERROR
            return False

        #pass 2: function names get their type from the header keyword
        self._register_function_headers(root)

        #pass 3: bottom-up type analysis
        self._visit(root)
        
        ok = (root.type ==OK)
        if not ok and root.type != ERROR and not self.errors:
            #guarding against silently unknown roots
            self.errors.append(SPLTypeError(
                "SPL_PROG did not reach type 'ok'. ",
                line=getattr(root, "line", None), node=root,
            ))
        
        if strict and self.errors:
            raise SPLTypeAnalysisFailed(self.errors)
        
        return ok and not self.errors
        
    #global crude rule: mod/div conflict + no decimal dot under mod
    
    def check_mod_div_conflict(self, root: Node) -> Optional[SPLTypeError]:
        first_mod: Optional[Node] = None
        first_div: Optional[Node] = None
        num_leaves_with_dot: List[Node] = []

        # iterative pre-order walk (source order), so long programs can't hit
        # Python's recursion limit here
        stack = [root]
        while stack:
            n = stack.pop()
            if n.kind == Kind.TERM_MOD:
                first_mod = first_mod or n
            elif n.kind == Kind.TERM_DIV:
                first_div = first_div or n
            elif n.kind == Kind.NUM:
                if n.value is not None and "." in n.value:
                    num_leaves_with_dot.append(n)
            stack.extend(reversed(n.children))

        # whole numbers if mod is used (or no decimals at all), real numbers otherwise
        if first_mod is not None:
            self.number_type = INT
        elif first_div is not None or num_leaves_with_dot:
            self.number_type = FLOAT
        else:
            self.number_type = INT

        def at(n: Node) -> str:
            return f"line {n.line}" if n.line is not None else "unknown line"

        if first_mod is not None and first_div is not None:
            # spec wording first; the locations are extra help for the user
            return SPLTypeError(
                f"{FLOAT_INT_CONFLICT_MSG} "
                f"('mod' at {at(first_mod)}, 'div' at {at(first_div)})",
                line=first_div.line if first_div.line is not None else root.line,
                node=root,
            )

        if first_mod is not None and num_leaves_with_dot:
            offenders = ", ".join(
                f"'{n.value}'" + (f" (line {n.line})" if n.line is not None else "")
                for n in num_leaves_with_dot
            )
            return SPLTypeError(
                f"A decimal dot is not allowed anywhere in the program when 'mod' is used "
                f"('mod' at {at(first_mod)}), but found: {offenders}",
                line=num_leaves_with_dot[0].line, node=root,
            )

        return None

    def _register_function_headers(self, root: Node) -> None:
        """Type every function name from its header keyword before the main walk.

        Without this, a function whose body has a type error never gets its
        name typed, so every call to it is reported again as 'undeclared'.
        The bottom-up rules for F_TYPE still run as normal afterwards.
        """
        stack = [root]
        while stack:
            n = stack.pop()
            if n.kind in (Kind.F_TYPE_VOID, Kind.F_TYPE_NUM):
                count, params = 0, n.children[1]
                while params.kind == Kind.V_DECL_CONS:
                    count, params = count + 1, params.children[1]
                self._arity[self._name_sys(n.children[0])] = count
            if n.kind == Kind.F_TYPE_VOID:
                self._set_name_type(n.children[0], PROCEDURE)
            elif n.kind == Kind.F_TYPE_NUM:
                self._set_name_type(n.children[0], NUMERIC)
            stack.extend(n.children)
    
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
        
    # function declarations always report, even when the fault is deeper down:
    # "which function does this break" is useful context, not noise
    _CONTEXT_KINDS = frozenset({Kind.F_TYPE_VOID, Kind.F_TYPE_NUM})

    def _fail(self, node: Node, message: str) -> None:
        #reports a type error at `node` and marks it ERROR so ancestors know this subtree is broken.
        #if a child is already ERROR, that error was reported where it happened, so this node
        #just inherits ERROR silently (every rule except the _CONTEXT_KINDS above)
        if node.kind not in self._CONTEXT_KINDS and any(c.type == ERROR for c in node.children):
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
            if algo.type != OK:
                bad.append("ALGO")
            self._fail(n, f"P is not well-typed: {', '.join(bad)} did not resolve to 'ok'.")
    
    def _r_v_decl_eps(self, n: Node) -> None:
        #V_DECL -> epsilon    (nullable) => "ok"
        n.type = OK
        
    def _r_v_decl_cons(self, n: Node) -> None:
        #V_DECL -> NAME V_DECL
        name, tail = n.children
        if tail.type == OK:
            self._set_name_type(name, NUMERIC)
            n.type = OK if name.type != ERROR else ERROR
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
            n.type = OK if name.type != ERROR else ERROR
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
            self._set_name_type(name, NUMERIC)
            n.type = OK if name.type != ERROR else ERROR
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
            self._fail(
                n,
                f"A call used as an instruction must target a 'void' (procedure) function, "
                f"but this call resolved to type '{call.type}'.",
            )
                
    def _r_call(self, n: Node) -> None:
        #CALL -> NAME ( INPUT )   if type_of(INPUT) is "ok" and type_of(NAME) =/= 'unknown: type_of(CALL) := type_of(NAME)
        name, inp = n.children
        name_type = self._get_name_type(name)
        expected = self._arity.get(self._name_sys(name))
        given, args = 0, inp
        while args.kind == Kind.INPUT_CONS:
            given, args = given + 1, args.children[1]
        if expected is not None and given != expected and inp.type == OK:
            # not in the 2b sheet, but code generation cannot inline such a call
            self._fail(n, f"Call to '{name.value}' passes {given} argument(s), "
                          f"but the function declares {expected} parameter(s).")
        elif inp.type == OK and name_type != UNKNOWN and name_type != ERROR:
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