import re

from semantics.ast_nodes import Kind

BINARY_OPS = {
    Kind.TERM_ADD: "+",
    Kind.TERM_SUB: "-",
    Kind.TERM_MUL: "*",
    Kind.TERM_DIV: "/",
    Kind.TERM_MOD: "%",
}

COMPARE_OPS = {
    Kind.BOOL_EQ: "==",
    Kind.BOOL_LARGER: ">",
    Kind.BOOL_LESSER: "<",
}

def generate_program(ast, symtab, number_type):
    """Return generated C++ source for an SPL program (spec parts 3a + 3b).

    Layout:  non-executable code-mine (one /* ... */ comment holding every
    function body, with their own sub-calls already inlined), then the
    executable main(): variable declarations, translated ALGO, return 0.
    """
    number_type = number_type or "int"
    gen = CodeGenerator(number_type)
    program = ast.children[0] if ast.kind == Kind.SPL_PROG else ast
    v_decl, f_decl, algo = program.children        # P -> (V_DECL, F_DECL, ALGO)
    gen.register_functions(f_decl)

    mine = gen.trans_code_mine(f_decl)
    body = gen.trans_algo(algo)

    entries = sorted(
        ((name, info) for name, info in symtab.dump().items() if info.get("kind") == "var"),
        key=lambda kv: _sys_number(kv[0]),
    )
    main_vars = [n for n, i in entries if i.get("scope_level", 0) == 0]
    inline_vars = [n for n, i in entries if i.get("scope_level", 0) != 0]
    lines = [
        "/* begin of the non-executable code-mine for later inlining */",
        mine,
        "/* end of the non-executable code-mine */",
        "/* begin of executable C code */",
        "#include <iostream>",
        "int main()",
        "{",
    ]
    lines += [f"{number_type} {n};" for n in main_vars]
    if inline_vars:
        lines.append("/* parameters and locals of the inlined functions */")
        lines += [f"{number_type} {n};" for n in inline_vars]
    lines += [body, "return 0;", "} /* end of executable C */", ""]
    return "\n".join(lines)


def _sys_number(name):
    m = re.search(r"(\d+)$", name)
    return int(m.group(1)) if m else 0


def _to_mine_text(code):
    """Make generated code safe to sit inside one big /* ... */ comment:
    C comments do not nest, so inner /* x */ become // x, and any stray
    comment terminator is defused."""
    code = re.sub(r"/\*(.*?)\*/", r"//\1", code)
    return code.replace("*/", "* /")


class CodeGenerator:
    def __init__(self, number_type):
        self.typ = number_type      # "int" or "float", from the type analyser
        self._var_count = 0
        self._label_count = 0
        self._functions = {}        # internal function name -> F_TYPE node

    def register_functions(self, f_decl):
        """Remember every function of the program, however deeply nested.
        Internal names are unique program-wide (phase 2a), so one flat map
        is enough and no scope juggling is needed while inlining."""
        stack = [f_decl]
        while stack:
            node = stack.pop()
            for function in self._list_items(node, Kind.F_DECL_CONS):
                self._functions[function.children[0].sym_id] = function
                stack.append(function.children[2].children[1])   # body P -> F_DECL

    @staticmethod
    def _list_items(node, cons_kind):
        items = []
        while node.kind == cons_kind:
            items.append(node.children[0])
            node = node.children[1]
        return items

    # ---------- fresh names ----------

    def new_var(self):
        name = f"v{self._var_count}"
        self._var_count += 1
        return name

    def new_label(self):
        name = f"L{self._label_count}"
        self._label_count += 1
        return name

    # ---------- ALGO / INSTR ----------

    def trans_algo(self, node):
        parts = []
        while node.kind == Kind.ALGO_CONS:
            instr, node = node.children
            parts.append(self.trans_instr(instr))
        parts.append("/* end */")
        return "\n".join(parts)

    def trans_instr(self, node):
        k = node.kind
        if k == Kind.INSTR_PRINT:
            return self.trans_print(node.children[0])
        if k == Kind.INSTR_NOP:
            return "/* nop */"
        if k == Kind.INSTR_COMMENT:
            return f"/* {self._string_text(node).replace('*/', '* /')} */"
        if k == Kind.INSTR_ASSIGN:
            return self.trans_assign(node.children[0])
        if k == Kind.INSTR_CALL:
            return self.trans_call(node.children[0])
        if k == Kind.INSTR_BRANCH:
            return self.trans_branch(node.children[0])
        if k == Kind.INSTR_LOOP:
            return self.trans_loop(node.children[0])
        raise NotImplementedError(f"not implemented yet: {k}")

    def trans_print(self, outp):
        if outp.kind == Kind.OUTP_STRING:
            return f"std::cout << {outp.value};"
        v = self.new_var()
        code = self.trans_term(outp.children[0], v)
        return "\n".join([f"{self.typ} {v};", code, f"std::cout << {v};"])

    def trans_assign(self, node):
        name, term = node.children
        v = self.new_var()
        code = self.trans_term(term, v)
        return "\n".join([f"{self.typ} {v};", code, f"{name.sym_id} = {v};"])

    def trans_call(self, node, result=None):
        """Inline a function call at its call site (spec 3b)."""
        name = node.children[0]
        function = self._functions.get(name.sym_id)
        if function is None:
            raise ValueError(f"function definition not found for {name.value}")

        params = self._list_items(function.children[1], Kind.V_DECL_CONS)
        args = self._list_items(node.children[1], Kind.INPUT_CONS)
        if len(params) != len(args):
            raise ValueError(
                f"function {name.value} expects {len(params)} arguments, got {len(args)}"
            )
        if result is not None and function.kind != Kind.F_TYPE_NUM:
            raise ValueError(f"void function {name.value} used as a value")

        parts = ["/* call */"]
        # 1st: evaluate ALL arguments into fresh variables p1..pN.  Only then
        # copy them into the parameters; otherwise an argument that itself
        # calls the same function would overwrite parameters already set.
        captured = []
        for arg in args:
            p = self.new_var()
            captured.append(p)
            parts.extend([f"{self.typ} {p};", self.trans_term(arg, p)])
        for param, p in zip(params, captured):
            parts.append(f"{param.sym_id} = {p};")

        # 2nd: the function body (a fresh copy, so labels/temps stay unique)
        body, r = self.inline_body(function)
        parts.append(body)
        # 3rd: connect the callee's return variable with the caller's variable
        if result is not None:
            parts.append(f"{result} = {r};")
        return "\n".join(parts)

    def inline_body(self, function):
        """Code of a function body (+ evaluation of its return term).
        Returns (code, return_variable); return_variable is None for void."""
        body = function.children[2]            # P
        code = self.trans_algo(body.children[2])
        if function.kind != Kind.F_TYPE_NUM:
            return code, None
        r = function.children[0].sym_id + self.new_var()      # r = f ++ n
        ret = self.trans_term(function.children[3], r)
        return "\n".join([code, f"{self.typ} {r};", ret]), r

    def trans_code_mine(self, f_decl):
        """Non-executable code for every function (spec 3b: F_TYPE)."""
        out = []
        for function in self._functions.values():
            name = function.children[0]
            kind = "Function" if function.kind == Kind.F_TYPE_NUM else "void-procedure"
            params = self._list_items(function.children[1], Kind.V_DECL_CONS)
            code, r = self.inline_body(function)
            lines = [f"begin of code-mine for {kind} {name.sym_id} ({name.value})",
                     "Parameters for inlining:"]
            lines += [f"{self.typ} {p.sym_id};" for p in params] or [" "]
            lines += ["Body of the procedure:", code,
                      f"end of code-mine for {kind} {name.sym_id}"]
            if r is not None:
                lines.append(f"The result is found in the return value {r}")
            out.append(_to_mine_text("\n".join(lines)))
        return "/*\n" + "\n".join(out) + "\n*/" if out else "/* (no functions) */"

    # ---------- TERM ----------

    def trans_term(self, node, result):
        k = node.kind
        if k == Kind.TERM_NUM:
            num = node.children[0].value.replace("\u2013", "-")
            return f"{result} = {num};"
        if k == Kind.TERM_NAME:
            return f"{result} = {node.children[0].sym_id};"
        if k == Kind.TERM_CALL:
            return self.trans_call(node.children[0], result)
        if k in BINARY_OPS:
            x, y = self.new_var(), self.new_var()
            code1 = self.trans_term(node.children[0], x)
            code2 = self.trans_term(node.children[1], y)
            return "\n".join([
                f"{self.typ} {x};", f"{self.typ} {y};",
                code1, code2,
                f"{result} = {x} {BINARY_OPS[k]} {y};",
            ])
        if k == Kind.TERM_NEG:
            x = self.new_var()
            code = self.trans_term(node.children[0], x)
            return "\n".join([f"{self.typ} {x};", code, f"{result} = -{x};"])
        raise NotImplementedError(f"unsupported TERM: {k}")


    # ---------- BOOL ----------
    # Control always ends at exactly one of the two labels.

    def trans_bool(self, node, l_true, l_false):
        k = node.kind
        if k in COMPARE_OPS:
            x, y = self.new_var(), self.new_var()
            code1 = self.trans_term(node.children[0], x)
            code2 = self.trans_term(node.children[1], y)
            return "\n".join([
                f"{self.typ} {x};", f"{self.typ} {y};",
                code1, code2,
                f"if ({x} {COMPARE_OPS[k]} {y}) goto {l_true};",
                f"goto {l_false};",
            ])
        if k == Kind.BOOL_NOT:
            return self.trans_bool(node.children[0], l_false, l_true)
        if k == Kind.BOOL_OR:
            l_next = self.new_label()
            first = self.trans_bool(node.children[0], l_true, l_next)
            second = self.trans_bool(node.children[1], l_true, l_false)
            return "\n".join([first, self.label(l_next), second])
        if k == Kind.BOOL_AND:
            l_next = self.new_label()
            first = self.trans_bool(node.children[0], l_next, l_false)
            second = self.trans_bool(node.children[1], l_true, l_false)
            return "\n".join([first, self.label(l_next), second])
        raise NotImplementedError(f"not implemented yet: {k}")

    def label(self, name, comment=""):
        return f"{name}: ; /* {comment} */" if comment else f"{name}: ;"
    # ---------- BRANCH ----------

    def trans_branch(self, node):
        cond, algo_true, algo_false = node.children
        la, lb, lc = self.new_label(), self.new_label(), self.new_label()
        decision = self.trans_bool(cond, la, lb)      # true -> La, false -> Lb
        true_code = self.trans_algo(algo_true)
        false_code = self.trans_algo(algo_false)
        return "\n".join([
            "/* if */", decision,
            self.label(lb, "else"), false_code, f"goto {lc};",
            self.label(la, "then"), true_code,
            self.label(lc, "continue"),
        ])

    # ---------- LOOP ----------

    def trans_loop(self, node):
        if node.kind == Kind.LOOP_PRE:                # COND BOOL do { ALGO }
            cond, cond_bool, body = node.children
            until = cond.kind == Kind.COND_UNTIL
            ls, le, d = self.new_label(), self.new_label(), self.new_label()
            # until: exit when true.  while: exit when false (= until not(BOOL))
            decision = (self.trans_bool(cond_bool, le, d) if until
                        else self.trans_bool(cond_bool, d, le))
            body_code = self.trans_algo(body)
            return "\n".join([
                self.label(ls, "until" if until else "while"),
                decision,
                self.label(d, "do"),
                body_code,
                f"goto {ls};",
                self.label(le, "exit"),
            ])
        # LOOP_POST:  do { ALGO } COND BOOL
        body, cond, cond_bool = node.children
        until = cond.kind == Kind.COND_UNTIL
        ld, le = self.new_label(), self.new_label()
        # while: repeat when true.  until: repeat when false.
        decision = (self.trans_bool(cond_bool, le, ld) if until
                    else self.trans_bool(cond_bool, ld, le))
        body_code = self.trans_algo(body)
        return "\n".join([
            self.label(ld, "do"), body_code, decision, self.label(le, "exit"),
        ])

    # ---------- helpers ----------

    def _string_text(self, node):
        # INSTR_COMMENT layout not confirmed yet: accept value-on-node or a child
        if node.value is not None:
            return node.value
        return node.children[0].value