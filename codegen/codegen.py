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
    """Return generated C++ source for an SPL program."""
    gen = CodeGenerator(number_type)
    program = ast.children[0]
    gen.set_functions(program.children[1])
    algo = program.children[2]                # P -> (V_DECL, F_DECL, ALGO)
    body = gen.trans_algo(algo)
    decls = "\n".join(
        f"{number_type} {name};"
        for name, info in symtab.dump().items() if info.get("kind") == "var"
    )
    return f"#include <iostream>\nint main() {{\n{decls}\n{body}\nreturn 0;\n}}\n"

class CodeGenerator:
    def __init__(self, number_type):
        self.typ = number_type      # "int" or "float", from the type analyser
        self._var_count = 0
        self._label_count = 0
        self._functions = {}

    def set_functions(self, f_decl):
        """Set the functions visible in the current block."""
        self._functions = {
            function.children[0].sym_id: function
            for function in self._list_items(f_decl, Kind.F_DECL_CONS)
        }

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
            return f"/* {self._string_text(node)} */"
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
        """Inline a function call at its call site."""
        function = self._functions.get(node.children[0].sym_id)
        if function is None:
            raise ValueError(f"function definition not found for {node.children[0].value}")

        params = self._list_items(function.children[1], Kind.V_DECL_CONS)
        args = self._list_items(node.children[1], Kind.INPUT_CONS)
        if len(params) != len(args):
            raise ValueError(
                f"function {node.children[0].value} expects {len(params)} arguments, "
                f"got {len(args)}"
            )

        parts = ["/* call */"]
        for param, arg in zip(params, args):
            value = self.new_var()
            parts.extend([
                f"{self.typ} {value};",
                self.trans_term(arg, value),
                f"{param.sym_id} = {value};",
            ])

        body = function.children[2]
        previous_functions = self._functions
        self.set_functions(body.children[1])
        parts.append(self.trans_algo(body.children[2]))
        if result is not None:
            if function.kind != Kind.F_TYPE_NUM:
                raise ValueError(f"void function {node.children[0].value} used as a value")
            parts.append(self.trans_term(function.children[3], result))
        self._functions = previous_functions
        return "\n".join(parts)

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
        raise NotImplementedError(f"not implemented yet: {k}")   # TERM_CALL is 3b


        def label(self, name, comment=""):
            return f"{name}: ; /* {comment} */" if comment else f"{name}: ;"

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