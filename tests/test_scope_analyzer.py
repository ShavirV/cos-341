"""Tests for phase 2a: scope analysis and unique renaming (semantics/scope_analyzer.py)."""

import unittest

from lexer.lexer import tokenize
from parser.parser import parse_tokens
from semantics.cst_to_ast import convert
from semantics.scope_analyzer import ScopeAnalyzer
from semantics.symbol_table import SymbolTable
from semantics.type_analyzer import TypeAnalyzer
from spl_pipeline import analyze
from xmlwriter.node import NodeIDGenerator


def run(src):
    NodeIDGenerator.reset()
    ast = convert(parse_tokens(tokenize(src)))
    st = SymbolTable()
    sa = ScopeAnalyzer(st)
    ok = sa.analyze(ast)
    return ok, sa.errors, ast, st


def names(ast):
    """[(orig, new, line)] for every NAME node, in source order."""
    out, stack = [], [ast]
    while stack:
        n = stack.pop()
        if n.kind == "NAME":
            out.append((n.value, n.sym_id, n.line))
        stack.extend(reversed(n.children))
    return out


def new_names(ast, orig):
    return [new for o, new, _ in names(ast) if o == orig]


# Announcement #21: f(g(j), h(k)); x declared in g, used in j (ok) and in k (sideways!)
SIDEWAYS = """
:
num #f ( ) {
  :
  num #g ( ) {
    #x
    :
    num #j ( ) { : : return ( #x ) }
    :
    return ( #j ( ) )
  }
  num #h ( ) {
    :
    num #k ( ) { : : return ( #x ) }
    :
    return ( #k ( ) )
  }
  :
  return ( add ( #g ( ) #h ( ) ) )
}
:
nop ;
"""


class VariableRules(unittest.TestCase):
    def test_simple_program_ok_and_renamed_consistently(self):
        ok, errs, ast, st = run("#x : : #x = 1 ; print ( #x ) ;")
        self.assertTrue(ok, errs)
        news = new_names(ast, "#x")
        self.assertEqual(len(news), 3)
        self.assertEqual(len(set(news)), 1)
        self.assertNotEqual(news[0], "#x")
        self.assertEqual(st.get(news[0])["orig_name"], "#x")
        self.assertEqual(st.get(news[0])["scope_level"], 0)

    def test_undeclared_variable(self):
        ok, errs, _, _ = run(": :\n#ghost = 1 ;")
        self.assertFalse(ok)
        self.assertEqual([(e.line, "no declaration" in e.message) for e in errs], [(2, True)])

    def test_nearest_declaration_wins_and_gets_other_name(self):
        src = ("#x : num #f ( #x ) { : : return ( #x ) } : #x = 1 ; "
               "#x = #f ( #x ) ;")
        ok, errs, ast, st = run(src)
        self.assertTrue(ok, errs)
        xs = new_names(ast, "#x")
        # order: global decl, param, return-use (param), 2 uses in main (global) + call arg (global)
        glob, param, ret = xs[0], xs[1], xs[2]
        self.assertNotEqual(glob, param)
        self.assertEqual(ret, param)
        self.assertEqual(xs[3:], [glob, glob, glob])
        self.assertEqual(st.get(param)["scope_level"], 1)

    def test_inner_function_sees_enclosing_variables_and_params(self):
        src = ("#a : num #f ( #p ) { #q : num #g ( ) { : : return ( add ( #p add ( #q #a ) ) ) } : "
               "return ( #g ( ) ) } : nop ;")
        ok, errs, _, _ = run(src)
        self.assertTrue(ok, errs)

    def test_sideways_declaration_not_visible(self):          # Announcement #21
        ok, errs, ast, st = run(SIDEWAYS)
        self.assertFalse(ok)
        self.assertEqual(len(errs), 1)
        self.assertIn("#x", errs[0].message)
        self.assertEqual(errs[0].line, 14)                     # the x used inside k

    def test_announcement_21_naming_with_separate_declaration_in_h(self):
        # give h its own x: now the two x of g/j are one entity, the x of k another
        src = SIDEWAYS.replace("  num #h ( ) {\n    :", "  num #h ( ) {\n    #x\n    :")
        ok, errs, ast, st = run(src)
        self.assertTrue(ok, errs)
        xs = new_names(ast, "#x")
        self.assertEqual(len(xs), 4)                           # decl g, use j, decl h, use k
        blue1, blue2, red_decl, red_use = xs
        self.assertEqual(blue1, blue2)
        self.assertEqual(red_decl, red_use)
        self.assertNotEqual(blue1, red_decl)

    def test_same_name_in_unrelated_functions_gets_different_names(self):
        src = (": num #f ( #n ) { : : return ( #n ) } num #g ( #n ) { : : return ( #n ) } : nop ;")
        ok, errs, ast, _ = run(src)
        self.assertTrue(ok, errs)
        n = new_names(ast, "#n")
        self.assertEqual(n[0], n[1])
        self.assertEqual(n[2], n[3])
        self.assertNotEqual(n[0], n[2])

    def test_duplicate_global_declaration(self):
        ok, errs, _, _ = run("#x #x : : nop ;")
        self.assertFalse(ok)
        self.assertIn("more than once", errs[0].message)

    def test_duplicate_parameter(self):
        ok, errs, _, _ = run(": void #f ( #a #a ) { : : return } : nop ;")
        self.assertFalse(ok)
        self.assertIn("parameter", errs[0].message)

    def test_local_masking_parameter_is_error(self):
        ok, errs, _, _ = run(": void #f ( #a ) { #a : : return } : nop ;")
        self.assertFalse(ok)
        self.assertEqual(len(errs), 1)
        self.assertIn("masks the parameter", errs[0].message)

    def test_local_shadowing_outer_variable_is_fine(self):
        ok, errs, ast, _ = run("#a : void #f ( ) { #a : : return } : nop ;")
        self.assertTrue(ok, errs)
        a = new_names(ast, "#a")
        self.assertNotEqual(a[0], a[1])

    def test_all_errors_collected_and_sorted_by_line(self):
        ok, errs, _, _ = run(": :\n#a = 1 ;\n#b = 2 ;\n#c = 3 ;")
        self.assertEqual([e.line for e in errs], [2, 3, 4])

    def test_uses_in_branch_and_loops_are_resolved(self):
        src = ("#x : : if eq ( #x 0 ) then { #x = 1 ; } else { #y = 2 ; } ; "
               "while larger ( #x 0 ) do { #z = 1 ; } ; "
               "do { nop ; } until eq ( #w 0 ) ;")
        ok, errs, _, _ = run(src)
        self.assertEqual(sorted(e.message.split("'")[1] for e in errs), ["#w", "#y", "#z"])


class FunctionRules(unittest.TestCase):
    def test_call_to_declared_function_ok(self):
        ok, errs, ast, st = run(": void #f ( ) { : : return } : #f ( ) ;")
        self.assertTrue(ok, errs)
        f = new_names(ast, "#f")
        self.assertEqual(f[0], f[1])
        self.assertEqual(st.get(f[0])["kind"], "func")
        self.assertEqual(st.get(f[0])["scope_level"], 1)

    def test_undeclared_function(self):
        ok, errs, _, _ = run(": : #nope ( 1 ) ;")
        self.assertFalse(ok)
        self.assertIn("no declaration", errs[0].message)

    def test_direct_recursion_is_rejected(self):
        ok, errs, _, _ = run(": void #f ( ) { : : #f ( ) ; return } : #f ( ) ;")
        self.assertFalse(ok)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].line, 1)
        self.assertIn("outer scope level", errs[0].message)

    def test_indirect_recursion_is_rejected(self):
        src = (": void #f ( ) { : : #g ( ) ; return } "
               "void #g ( ) { : : #f ( ) ; return } : #f ( ) ;")
        ok, errs, _, _ = run(src)
        self.assertFalse(ok)
        self.assertEqual(len(errs), 2)             # f cannot see sibling g, g cannot see f

    def test_main_cannot_call_subfunction(self):
        src = ": void #f ( ) { : void #g ( ) { : : return } : #g ( ) ; return } : #g ( ) ;"
        ok, errs, _, _ = run(src)
        self.assertFalse(ok)
        self.assertEqual(len(errs), 1)             # only the call in main fails

    def test_subfunction_cannot_call_parents_sibling(self):
        src = (": void #h ( ) { : : return } "
               "void #f ( ) { : void #g ( ) { : : #h ( ) ; return } : #g ( ) ; return } : #f ( ) ;")
        ok, errs, _, _ = run(src)
        self.assertFalse(ok)
        self.assertIn("outer scope level", errs[0].message)

    def test_shared_helper_must_be_duplicated(self):
        # the spec's own comment: h has to be written twice, once under each user
        src = (": void #f ( ) { : void #h ( ) { : : return } : #h ( ) ; return } "
               "void #g ( ) { : void #h ( ) { : : return } : #h ( ) ; return } : #f ( ) ; #g ( ) ;")
        ok, errs, ast, _ = run(src)
        self.assertTrue(ok, errs)
        h = new_names(ast, "#h")
        self.assertEqual((h[0], h[1]), (h[0], h[0]))
        self.assertEqual(h[2], h[3])
        self.assertNotEqual(h[0], h[2])

    def test_function_name_unique_per_level(self):
        ok, errs, _, _ = run(": void #f ( ) { : : return } void #f ( ) { : : return } : nop ;")
        self.assertFalse(ok)
        self.assertIn("more than once", errs[0].message)

    def test_same_function_name_at_different_levels_is_fine(self):
        src = ": void #f ( ) { : void #f ( ) { : : return } : #f ( ) ; return } : #f ( ) ;"
        ok, errs, ast, _ = run(src)
        self.assertTrue(ok, errs)
        f = new_names(ast, "#f")
        self.assertNotEqual(f[0], f[1])            # outer f vs inner f
        self.assertEqual(f[1], f[2])               # call inside f -> the INNER f
        self.assertEqual(f[0], f[3])               # call in main -> the outer f

    def test_return_term_uses_function_body_scope(self):
        src = (": num #f ( #p ) { #l : num #g ( ) { : : return ( 1 ) } : #l = 2 ; "
               "return ( add ( add ( #p #l ) #g ( ) ) ) } : nop ;")
        ok, errs, _, _ = run(src)
        self.assertTrue(ok, errs)

    def test_variable_and_function_namespaces_are_separate(self):
        ok, errs, ast, st = run("#f : num #f ( ) { : : return ( 1 ) } : #f = #f ( ) ;")
        self.assertTrue(ok, errs)
        a, b, c, d = new_names(ast, "#f")
        self.assertEqual((a, c, b, d), (a, a, b, b))
        self.assertNotEqual(a, b)

    def test_function_used_as_variable_and_vice_versa(self):
        ok, errs, _, _ = run("#x : void #f ( ) { : : return } : #x = #f ;")
        self.assertIn("only declared as a function", errs[0].message)
        ok, errs, _, _ = run("#v : : #v ( ) ;")
        self.assertIn("only declared as a variable", errs[0].message)


class SymbolTableAndPipeline(unittest.TestCase):
    def test_new_names_are_unique_per_entity(self):
        ok, errs, ast, st = run("#a #b : void #f ( #a ) { #c : : return } : nop ;")
        self.assertTrue(ok, errs)
        self.assertEqual(len(st.dump()), 5)            # a, b, f, a(param), c
        self.assertEqual(len({n for _, n, _ in names(ast)}), 5)

    def test_every_renamed_node_is_in_symbol_table(self):
        _, _, ast, st = run(SIDEWAYS.replace("return ( #x ) }\n    :\n    return ( #k", "return ( 1 ) }\n    :\n    return ( #k"))
        for _, new, _ in names(ast):
            self.assertTrue(st.has(new), new)

    def test_original_spelling_is_kept_in_value(self):
        _, _, ast, _ = run("#x : : #x = 1 ;")
        self.assertTrue(all(o == "#x" for o, _, _ in names(ast)))

    def test_strict_mode_raises(self):
        from semantics.errors import SPLScopeAnalysisFailed
        ast = convert(parse_tokens(tokenize(": : #q = 1 ;")))
        with self.assertRaises(SPLScopeAnalysisFailed):
            ScopeAnalyzer().analyze(ast, strict=True)

    def test_type_analysis_after_renaming_uses_internal_names(self):
        # variable and function share a spelling -> without renaming this is a type conflict
        src = "#f : num #f ( ) { : : return ( 1 ) } : #f = #f ( ) ;"
        NodeIDGenerator.reset()
        ast = convert(parse_tokens(tokenize(src)))
        st = SymbolTable()
        self.assertTrue(ScopeAnalyzer(st).analyze(ast))
        ta = TypeAnalyzer(st)
        self.assertTrue(ta.analyze(ast, strict=False), ta.errors)
        kinds = {e["orig_name"]: e["type"] for e in st.dump().values()}
        self.assertEqual(kinds["#f"] in ("numeric",), True)
        # the type info must not have clobbered the scope info
        self.assertTrue(all("scope_level" in e for e in st.dump().values()))

    def test_pipeline_scope_problem_kind_and_line(self):
        r = analyze(": :\n#ghost = 1 ;\n", scopecheck=True)
        self.assertTrue(r.syntax_ok and r.scope_checked)
        self.assertEqual([(p.kind, p.line) for p in r.problems], [("scope", 2)])

    def test_pipeline_typecheck_implies_scope_and_skips_types_on_scope_errors(self):
        r = analyze(": :\n#ghost = 1 ;\n", typecheck=True)
        self.assertEqual([(p.kind, p.line) for p in r.problems], [("scope", 2)])
        self.assertFalse(r.type_checked)

    def test_pipeline_ok_program(self):
        r = analyze("#x : : #x = 1 ;\nprint ( #x ) ;\n", typecheck=True)
        self.assertTrue(r.ok and r.scope_checked and r.type_checked)
        self.assertEqual(len(r.symtab.dump()), 1)

    def test_very_long_programs_do_not_hit_the_recursion_limit(self):
        # cst_to_ast is recursive, so build a 20000-statement AST by hand:
        # the scope analyzer itself must be iterative.
        from semantics.ast_nodes import Node, Kind
        decl = Node(Kind.V_DECL_CONS, [Node(Kind.NAME, value="#x", line=1), Node(Kind.V_DECL_EPS)])
        algo = Node(Kind.ALGO_EPS)
        for _ in range(20000):
            asg = Node(Kind.INSTR_ASSIGN, [Node(Kind.ASSIGN, [
                Node(Kind.NAME, value="#x", line=2),
                Node(Kind.TERM_NUM, [Node(Kind.NUM, value="1")])])])
            algo = Node(Kind.ALGO_CONS, [asg, algo])
        root = Node(Kind.SPL_PROG, [Node(Kind.P, [decl, Node(Kind.F_DECL_EPS), algo])])
        sa = ScopeAnalyzer()
        self.assertTrue(sa.analyze(root), sa.errors[:1])

    def test_deeply_nested_functions(self):
        depth = 150      # f nested in f nested in f ... (same spelling, different levels)
        src = ": " + "void #f ( ) { : " * (depth - 1) + "void #f ( ) { : : return } " \
              + ": return } " * (depth - 1) + ": nop ;"
        ok, errs, _, _ = run(src)
        self.assertTrue(ok, errs[:2])


if __name__ == "__main__":
    unittest.main()
