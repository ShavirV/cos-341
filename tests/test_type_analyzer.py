"""
Tests for Type Analyzer.

These build small syntax trees using ast_nodes.Node
Each test targets one rule or one error condition straight from the spec.

"""

from ast_nodes import Node, Kind
from symbol_table import SymbolTable
from type_analyzer import TypeAnalyzer, OK, NUMERIC, BOOLEAN, PROCEDURE
from errors import SPLTypeAnalysisFailed



#small builder helpers to keep tests readable

def NAME(sys_name, line=None):
    return Node(Kind.NAME, value=sys_name, line=line, sym_id=sys_name)


def NUM(text, line=None):
    return Node(Kind.NUM, value=text, line=line)


def STRING(text="\"hi\"", line=None):
    return Node(Kind.STRING, value=text, line=line)


def v_decl(*names):
    """Build a V_DECL chain from a list of NAME nodes (or sys-name strings)."""
    node = Node(Kind.V_DECL_EPS)
    for nm in reversed(names):
        name_node = nm if isinstance(nm, Node) else NAME(nm)
        node = Node(Kind.V_DECL_CONS, children=[name_node, node])
    return node


def f_decl(*f_types):
    node = Node(Kind.F_DECL_EPS)
    for ft in reversed(f_types):
        node = Node(Kind.F_DECL_CONS, children=[ft, node])
    return node


def algo(*instrs):
    node = Node(Kind.ALGO_EPS)
    for ins in reversed(instrs):
        node = Node(Kind.ALGO_CONS, children=[ins, node])
    return node


def instr_assign(name_sys, term):
    return Node(Kind.INSTR_ASSIGN, children=[Node(Kind.ASSIGN, children=[NAME(name_sys), term])])


def instr_print_term(term):
    return Node(Kind.INSTR_PRINT, children=[Node(Kind.OUTP_TERM, children=[term])])


def instr_print_string(text='"hello"'):
    return Node(Kind.INSTR_PRINT, children=[Node(Kind.OUTP_STRING, value=text)])


def instr_nop():
    return Node(Kind.INSTR_NOP)


def instr_call(name_sys, *arg_terms):
    inp = Node(Kind.INPUT_EPS)
    for t in reversed(arg_terms):
        inp = Node(Kind.INPUT_CONS, children=[t, inp])
    return Node(Kind.INSTR_CALL, children=[Node(Kind.CALL, children=[NAME(name_sys), inp])])


def term_name(sys_name):
    return Node(Kind.TERM_NAME, children=[NAME(sys_name)])


def term_num(text):
    return Node(Kind.TERM_NUM, children=[NUM(text)])


def term_bin(kind, t1, t2):
    return Node(kind, children=[t1, t2])


def term_call(name_sys, *arg_terms):
    inp = Node(Kind.INPUT_EPS)
    for t in reversed(arg_terms):
        inp = Node(Kind.INPUT_CONS, children=[t, inp])
    return Node(Kind.TERM_CALL, children=[Node(Kind.CALL, children=[NAME(name_sys), inp])])


def prog(v, f, a):
    p = Node(Kind.P, children=[v, f, a])
    return Node(Kind.SPL_PROG, children=[p])


def run(root):
    ta = TypeAnalyzer()
    ok = ta.analyze(root, strict=False)
    return ok, ta.errors, ta.symtab


# 1. A minimal, entirely correct program: var x; x = 3; print(x);

def test_simple_correct_program():
    v = v_decl("x_1")
    a = algo(
        instr_assign("x_1", term_num("3")),
        instr_print_term(term_name("x_1")),
    )
    root = prog(v, f_decl(), a)

    ok, errors, symtab = run(root)
    assert ok, errors
    assert errors == []
    assert symtab.get_type("x_1") == NUMERIC

# 2. Use of an undeclared variable => TERM -> NAME rule fails (type "unknown")

def test_undeclared_variable_is_error():
    v = v_decl()  # no declarations at all
    a = algo(instr_print_term(term_name("y_undeclared")))
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert not ok
    assert any("y_undeclared" in e.message for e in errors)


# 3. Assigning a boolean-shaped expression to a NAME (type mismatch)

def test_assign_type_mismatch():
    # f is declared as a void function (=> "procedure"), then used as a TERM via a numeric assignment target/source mismatch.
    f_body_v = v_decl()
    f_body_a = algo(instr_nop())
    void_func = Node(Kind.F_TYPE_VOID, children=[NAME("f_1"), f_body_v,
                                                  Node(Kind.P, children=[f_body_v, f_decl(), f_body_a])])

    v = v_decl("x_1")
    a = algo(
        instr_call("f_1"),                       # ok: void call as statement
        instr_assign("x_1", term_name("f_1")),    # ERROR: f_1 is procedure, not numeric
    )
    root = prog(v, f_decl(void_func), a)

    ok, errors, _ = run(root)
    assert not ok
    assert any("f_1" in e.message for e in errors)


# 4. mod(...) and div(...) both present anywhere => outright global rejection

def test_mod_div_conflict_rejects_whole_tree():
    v = v_decl("x_1")
    mod_term = term_bin(Kind.TERM_MOD, term_num("3"), term_num("2"))
    div_term = term_bin(Kind.TERM_DIV, term_num("4"), term_num("2"))
    a = algo(
        instr_assign("x_1", mod_term),
        instr_print_term(div_term),
    )
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert not ok
    assert len(errors) == 1
    assert "float-integer-conflict" in errors[0].message


# 5. mod(...) present + a NUM literal with a decimal dot anywhere => reject


def test_mod_forbids_decimal_dot_anywhere():
    v = v_decl("x_1", "y_1")
    mod_term = term_bin(Kind.TERM_MOD, term_num("5"), term_num("2"))
    a = algo(
        instr_assign("x_1", mod_term),
        instr_assign("y_1", term_num("3.14")),   # decimal dot, forbidden once mod is used
    )
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert not ok
    assert len(errors) == 1
    assert "decimal dot" in errors[0].message
    assert "3.14" in errors[0].message


def test_mod_alone_with_integers_is_fine():
    v = v_decl("x_1")
    mod_term = term_bin(Kind.TERM_MOD, term_num("5"), term_num("2"))
    a = algo(instr_assign("x_1", mod_term))
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert ok, errors


def test_div_alone_with_decimal_is_fine():
    v = v_decl("x_1")
    div_term = term_bin(Kind.TERM_DIV, term_num("5.0"), term_num("2.0"))
    a = algo(instr_assign("x_1", div_term))
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert ok, errors


# 6. Calling a "num" function as a statement (INSTR -> CALL requires type_of(CALL) == "procedure") should fail.

def test_calling_num_function_as_statement_is_error():
    # num g() { <empty body> return (3) }
    g_v = v_decl()
    g_a = algo()
    g_p = Node(Kind.P, children=[g_v, f_decl(), g_a])
    num_func = Node(Kind.F_TYPE_NUM, children=[NAME("g_1"), g_v, g_p, term_num("3")])

    v = v_decl()
    a = algo(instr_call("g_1"))  # ERROR: g_1 is numeric, not procedure
    root = prog(v, f_decl(num_func), a)

    ok, errors, _ = run(root)
    assert not ok
    assert any("must target a 'void' (procedure) function" in e.message for e in errors)


# 7. Well-typed BRANCH and LOOP with boolean composition

def test_branch_and_loop_well_typed():
    v = v_decl("x_1")
    cond = term_bin(Kind.BOOL_LARGER, term_name("x_1"), term_num("0"))
    branch = Node(Kind.BRANCH, children=[
        cond,
        algo(instr_print_string()),
        algo(instr_nop()),
    ])
    loop_cond = Node(Kind.BOOL_NOT, children=[
        Node(Kind.BOOL_EQ, children=[term_name("x_1"), term_num("10")])
    ])
    loop = Node(Kind.LOOP_PRE, children=[
        Node(Kind.COND_WHILE),
        loop_cond,
        algo(instr_assign("x_1", term_bin(Kind.TERM_ADD, term_name("x_1"), term_num("1")))),
    ])
    a = algo(
        Node(Kind.INSTR_BRANCH, children=[branch]),
        Node(Kind.INSTR_LOOP, children=[loop]),
    )
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert ok, errors


def test_branch_with_non_boolean_condition_is_error():
    v = v_decl("x_1")
    bad_eq = Node(Kind.BOOL_EQ, children=[term_name("undeclared_var"), term_num("1")])
    branch = Node(Kind.BRANCH, children=[bad_eq, algo(instr_nop()), algo(instr_nop())])
    a = algo(Node(Kind.INSTR_BRANCH, children=[branch]))
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert not ok
    assert any("undeclared_var" in e.message for e in errors)


# 8. num-function whose return TERM isn't numeric-typed (undeclared name) fails

def test_num_function_bad_return_is_error():
    g_v = v_decl()
    g_a = algo()
    g_p = Node(Kind.P, children=[g_v, f_decl(), g_a])
    bad_return = term_name("never_declared")
    num_func = Node(Kind.F_TYPE_NUM, children=[NAME("g_1"), g_v, g_p, bad_return])

    root = prog(v_decl(), f_decl(num_func), algo())

    ok, errors, _ = run(root)
    assert not ok
    assert any("g_1" in e.message for e in errors)

# 9. Error-cascade dedup: one root-cause fault should not balloon into one message per ancestor node on the way back up to SPL_PROG.

def test_single_root_cause_yields_single_error():
    v = v_decl()  # no declarations
    a = algo(instr_print_term(term_name("ghost")))  # ghost is undeclared
    root = prog(v, f_decl(), a)

    ok, errors, _ = run(root)
    assert not ok
    # Exactly one error: the undeclared-name fault itself. Ancestor nodes
    # (OUTP_TERM, INSTR_PRINT, ALGO_CONS, P, SPL_PROG) are pure pass-through
    # here and must not each log their own "did not resolve to ok" entry.
    assert len(errors) == 1, f"expected exactly 1 error, got {len(errors)}: {errors}"
    assert "ghost" in errors[0].message


def test_cascade_still_names_the_broken_function():
    # A num-function whose return expression is broken should still yield a
    # message that names the function (not just the innermost fault),
    # because F_TYPE_NUM is not a pure pass-through node -- "which function
    # does this break" is itself useful context, not noise.
    g_v = v_decl()
    g_a = algo()
    g_p = Node(Kind.P, children=[g_v, f_decl(), g_a])
    bad_return = term_name("never_declared")
    num_func = Node(Kind.F_TYPE_NUM, children=[NAME("g_1"), g_v, g_p, bad_return])

    root = prog(v_decl(), f_decl(num_func), algo())

    ok, errors, _ = run(root)
    assert not ok
    assert any("never_declared" in e.message for e in errors)
    assert any("g_1" in e.message for e in errors)
    # Root cause + the one node that adds real context -- not a full
    # cascade all the way to SPL_PROG.
    assert len(errors) == 2, f"expected exactly 2 errors, got {len(errors)}: {errors}"


# 10. Defensive symbol-table check: two declaration sites disagreeing about
#     a sys_name's type is an internal-consistency fault  that must be surfaced, not silently
#     resolved by last-write-wins.

def test_conflicting_declared_types_for_same_sys_name_is_error():

    f_p = Node(Kind.P, children=[Node(Kind.V_DECL_EPS), f_decl(), algo()])
    void_func = Node(Kind.F_TYPE_VOID, children=[NAME("f_1"), Node(Kind.V_DECL_EPS), f_p])

    v = v_decl(NAME("f_1"))  # collides with the function's own sys_name
    root = prog(v, f_decl(void_func), algo())

    ok, errors, symtab = run(root)
    assert not ok
    assert any("conflicting types" in e.message and "f_1" in e.message for e in errors)



# main: allow running this file directly without pytest

if __name__ == "__main__":
    import sys
    import traceback

    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_") and callable(obj)]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
            passed += 1
        except AssertionError:
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
            failed += 1
        except Exception:
            print(f"ERROR: {t.__name__}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)}")
    sys.exit(1 if failed else 0)
