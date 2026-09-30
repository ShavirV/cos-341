"""Tests for spl_pipeline.analyze(), the display-free driver the GUI is built on."""

import unittest

from spl_pipeline import analyze

GOOD = "#x : : #x = 1 ;\nprint ( #x ) ;\n"


class AnalyzeTests(unittest.TestCase):
    def test_valid_program(self):
        r = analyze(GOOD)
        self.assertTrue(r.ok and r.syntax_ok)
        self.assertEqual(r.problems, [])
        self.assertIn("<tree>", r.xml)
        self.assertGreater(r.node_count, 10)
        self.assertEqual(r.xml.count("<node>"), r.node_count)

    def test_lexical_error_has_position_and_no_tree(self):
        r = analyze("#x : :\n#x = 05 ;\n")
        self.assertFalse(r.syntax_ok)
        p = r.problems[0]
        self.assertEqual((p.kind, p.line), ("lexical", 2))
        self.assertIsNotNone(p.col)
        self.assertEqual(r.xml, "")

    def test_syntax_error_has_position(self):
        r = analyze("#x : :\n#x = ;\n")
        p = r.problems[0]
        self.assertEqual((p.kind, p.line, p.col), ("syntax", 2, 6))
        self.assertIn("Hint", p.message)

    def test_unexpected_end_of_input_has_no_position(self):
        r = analyze("#x : : if eq ( 1 2 ) then {")
        p = r.problems[0]
        self.assertEqual(p.kind, "syntax")
        self.assertIsNone(p.line)
        self.assertIn("end of input", p.message)

    def test_dollar_is_rejected(self):
        self.assertEqual(analyze("#x : : nop ; $").problems[0].kind, "lexical")

    def test_type_errors_reported_but_tree_kept(self):
        r = analyze(": :\n#ghost = 1 ;\n", typecheck=True)
        self.assertTrue(r.syntax_ok)            # the tree/xml are still available
        self.assertFalse(r.ok)
        self.assertEqual([(p.kind, p.line) for p in r.problems], [("type", 2)])
        self.assertTrue(r.type_checked)

    def test_type_check_is_off_by_default(self):
        r = analyze(": :\n#ghost = 1 ;\n")
        self.assertTrue(r.ok)
        self.assertFalse(r.type_checked)

    def test_well_typed_program_passes_type_check(self):
        r = analyze(GOOD, typecheck=True)
        self.assertTrue(r.ok and r.type_checked)

    def test_ids_restart_on_every_call(self):
        first = analyze(GOOD).xml
        self.assertEqual(first, analyze(GOOD).xml)

    def test_very_long_program_does_not_crash(self):
        r = analyze(": : " + "nop ; " * 3000)
        self.assertTrue(r.syntax_ok)
        r = analyze(": : " + "nop ; " * 3000, typecheck=True)   # may report a problem, must not raise
        self.assertTrue(r.syntax_ok)


if __name__ == "__main__":
    unittest.main()
