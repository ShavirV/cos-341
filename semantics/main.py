from ast_nodes import Node, Kind
from type_analyzer import TypeAnalyzer
from errors import SPLTypeAnalysisFailed


def build_demo_program() -> Node:
    """
    Roughly:
        num x;
        num y;

        void greet() {
            comment "says hi";
            print "hello";
            return
        }

        num square(num n) {
            return (mul(n, n))
        }

        x = 5;
        y = square(x);
        greet();
        print(y);
    """
    def NAME(s, line=None):
        return Node(Kind.NAME, value=s, line=line, sym_id=s)

    def NUM(t, line=None):
        return Node(Kind.NUM, value=t, line=line)

    #function: void greet()
    greet_body_algo = Node(Kind.ALGO_CONS, children=[
        Node(Kind.INSTR_COMMENT, children=[Node(Kind.STRING, value='"says hi"')]),
        Node(Kind.ALGO_CONS, children=[
            Node(Kind.INSTR_PRINT, children=[Node(Kind.OUTP_STRING, value='"hello"')]),
            Node(Kind.ALGO_EPS),
        ]),
    ])
    greet_p = Node(Kind.P, children=[Node(Kind.V_DECL_EPS), Node(Kind.F_DECL_EPS), greet_body_algo])
    greet_func = Node(Kind.F_TYPE_VOID, children=[NAME("greet_1"), Node(Kind.V_DECL_EPS), greet_p])

    #function: num square(num n) { return (mul(n, n)) }
    square_params = Node(Kind.V_DECL_CONS, children=[NAME("n_1"), Node(Kind.V_DECL_EPS)])
    square_p = Node(Kind.P, children=[Node(Kind.V_DECL_EPS), Node(Kind.F_DECL_EPS), Node(Kind.ALGO_EPS)])
    square_return = Node(Kind.TERM_MUL, children=[
        Node(Kind.TERM_NAME, children=[NAME("n_1")]),
        Node(Kind.TERM_NAME, children=[NAME("n_1")]),
    ])
    square_func = Node(Kind.F_TYPE_NUM, children=[NAME("square_1"), square_params, square_p, square_return])

    f_decl = Node(Kind.F_DECL_CONS, children=[
        greet_func,
        Node(Kind.F_DECL_CONS, children=[square_func, Node(Kind.F_DECL_EPS)]),
    ])

    v_decl = Node(Kind.V_DECL_CONS, children=[
        NAME("x_1"),
        Node(Kind.V_DECL_CONS, children=[NAME("y_1"), Node(Kind.V_DECL_EPS)]),
    ])

    call_square = Node(Kind.TERM_CALL, children=[
        Node(Kind.CALL, children=[
            NAME("square_1"),
            Node(Kind.INPUT_CONS, children=[Node(Kind.TERM_NAME, children=[NAME("x_1")]), Node(Kind.INPUT_EPS)]),
        ])
    ])
    call_greet = Node(Kind.INSTR_CALL, children=[
        Node(Kind.CALL, children=[NAME("greet_1"), Node(Kind.INPUT_EPS)])
    ])

    main_algo = Node(Kind.ALGO_CONS, children=[
        Node(Kind.INSTR_ASSIGN, children=[Node(Kind.ASSIGN, children=[NAME("x_1"), Node(Kind.TERM_NUM, children=[NUM("5")])])]),
        Node(Kind.ALGO_CONS, children=[
            Node(Kind.INSTR_ASSIGN, children=[Node(Kind.ASSIGN, children=[NAME("y_1"), call_square])]),
            Node(Kind.ALGO_CONS, children=[
                call_greet,
                Node(Kind.ALGO_CONS, children=[
                    Node(Kind.INSTR_PRINT, children=[Node(Kind.OUTP_TERM, children=[Node(Kind.TERM_NAME, children=[NAME("y_1")])])]),
                    Node(Kind.ALGO_EPS),
                ]),
            ]),
        ]),
    ])

    p = Node(Kind.P, children=[v_decl, f_decl, main_algo])
    return Node(Kind.SPL_PROG, children=[p])


def main():
    root = build_demo_program()
    analyzer = TypeAnalyzer()

    try:
        ok = analyzer.analyze(root, strict=True)
        print("Type analysis PASSED. Program is well-typed.")
        print("\nFinal Symbol Table:")
        print(analyzer.symtab)
    except SPLTypeAnalysisFailed as e:
        print("Type analysis FAILED:")
        for err in e.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
