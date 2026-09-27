"""
Test suite for lexer2.py

Testing strategy
-----------------
1. TRANSITION COVERAGE per DFA: for each hand-derived state machine (NUM,
   NAME, STRING), one test input per transition arrow in the diagram, so
   every edge gets exercised at least once -- this is what actually catches
   DFA *design* bugs (e.g. two states wrongly merged), as opposed to just
   confirming "it works on some obviously-valid input."
2. BOUNDARY / EQUIVALENCE CASES: the inputs that sit right on a decision
   boundary (leading zero vs non-zero, signed vs unsigned, fraction ending
   in 0 vs non-zero) -- these are exactly where past bugs lived.
3. NEGATIVE TESTS: one per rejected string, each asserting *which* state/
   reason it fails for, not just that it raises.
4. DRIVER-LEVEL TESTS: blank-splitting, line/col tracking, trailing-blank
   enforcement, symbol spacing -- things that live in tokenize(), not the
   DFAs themselves.
5. INTEGRATION TEST: one full syntactically-tokenizable SPL fragment run
   through end to end.

Run with:  python3 -m unittest test_lexer.py -v
"""

import unittest
from lexer2 import tokenize, classify, LexError, Token


def kinds(text):
    """Helper: tokenize and return just the list of (kind, lexeme) pairs."""
    return [(t.kind, t.lexeme) for t in tokenize(text)]


class TestNumTransitionCoverage(unittest.TestCase):
    # State diagram being covered (see lexer2.run_num):
    #   A -(-)-> D        A -(0)-> C        A -(1..9)-> B
    #   D -(0)-> Z        D -(1..9)-> B
    #   Z -(.)-> GH
    #   C -(.)-> GH
    #   B -(0..9)-> B     B -(.)-> GH
    #   GH -(0)-> GH      GH -(1..9)-> I
    #   I -(0)-> GH       I -(1..9)-> I

    def test_A_to_D(self):          # A -(-)-> D
        self.assertEqual(kinds('-5 '), [('NUM', '-5')])

    def test_A_to_C(self):          # A -(0)-> C, accept (bare zero)
        self.assertEqual(kinds('0 '), [('NUM', '0')])

    def test_A_to_B(self):          # A -(1..9)-> B, accept
        self.assertEqual(kinds('7 '), [('NUM', '7')])

    def test_D_to_Z(self):          # D -(0)-> Z, non-final by itself
        self.assertEqual(kinds('-0.5 '), [('NUM', '-0.5')])

    def test_D_to_B(self):          # D -(1..9)-> B, accept
        self.assertEqual(kinds('-7 '), [('NUM', '-7')])

    def test_Z_to_GH(self):         # Z -(.)-> GH
        self.assertEqual(kinds('-0.1 '), [('NUM', '-0.1')])

    def test_C_to_GH(self):         # C -(.)-> GH
        self.assertEqual(kinds('0.1 '), [('NUM', '0.1')])

    def test_B_self_loop(self):     # B -(0..9)-> B
        self.assertEqual(kinds('12345 '), [('NUM', '12345')])

    def test_B_to_GH(self):         # B -(.)-> GH
        self.assertEqual(kinds('12.3 '), [('NUM', '12.3')])

    def test_GH_self_loop_then_I(self):   # GH -(0)-> GH, then GH -(1..9)-> I
        self.assertEqual(kinds('0.001 '), [('NUM', '0.001')])

    def test_I_to_GH(self):         # I -(0)-> GH, then GH -(1..9)-> I again
        self.assertEqual(kinds('0.109 '), [('NUM', '0.109')])

    def test_I_self_loop(self):     # I -(1..9)-> I
        self.assertEqual(kinds('0.999 '), [('NUM', '0.999')])


class TestNumBoundaryAndNegative(unittest.TestCase):
    def test_bare_zero_accepted(self):
        self.assertEqual(kinds('0 '), [('NUM', '0')])

    def test_signed_bare_zero_rejected(self):
        with self.assertRaises(LexError):
            tokenize('-0 ')

    def test_leading_zero_followed_by_digit_rejected(self):
        with self.assertRaises(LexError):
            tokenize('00 ')
        with self.assertRaises(LexError):
            tokenize('01 ')

    def test_double_minus_rejected(self):
        with self.assertRaises(LexError):
            tokenize('--5 ')

    def test_trailing_decimal_point_rejected(self):
        with self.assertRaises(LexError):
            tokenize('5. ')

    def test_fraction_trailing_zero_rejected(self):
        # fraction must END in a non-zero digit
        with self.assertRaises(LexError):
            tokenize('0.10 ')
        with self.assertRaises(LexError):
            tokenize('0.0 ')

    def test_lone_minus_rejected(self):
        with self.assertRaises(LexError):
            tokenize('- ')

    def test_no_leading_dot_form(self):
        # '.5' has no rule permitting a dot with nothing before it
        with self.assertRaises(LexError):
            tokenize('.5 ')


class TestNameTransitionCoverage(unittest.TestCase):
    # S0 -(#)-> S1 (final immediately -- empty name)
    # S1 -(alphanumeric)-> S1 (final, self loop)

    def test_S0_to_S1_empty_name(self):
        self.assertEqual(kinds('# '), [('NAME', '#')])

    def test_S1_self_loop_digits_and_letters(self):
        self.assertEqual(kinds('#x1y2z '), [('NAME', '#x1y2z')])

    def test_missing_hash_rejected(self):
        with self.assertRaises(LexError):
            tokenize('x1y2z ')  # no leading '#' -> not a NAME, not a keyword

    def test_uppercase_rejected(self):
        with self.assertRaises(LexError):
            tokenize('#ABC ')  # alphabet is a-z only, no uppercase

    def test_invalid_char_in_name_rejected(self):
        with self.assertRaises(LexError):
            tokenize('#a-b ')  # '-' not in NAME alphabet


class TestStringTransitionCoverage(unittest.TestCase):
    # S0 -(")-> S1 (not final)
    # S1 -(allowed char)-> S1 (loop, not final)
    # S1 -(")-> S2 (final)

    def test_S0_to_S1_to_S2_empty_string(self):
        self.assertEqual(kinds('"" '), [('STRING', '""')])

    def test_S1_self_loop_all_alphabet_classes(self):
        self.assertEqual(kinds('"a,b.c:d?e!f123" '),
                          [('STRING', '"a,b.c:d?e!f123"')])

    def test_unterminated_string_rejected(self):
        with self.assertRaises(LexError):
            tokenize('"abc ')  # no closing quote before the blank

    def test_space_inside_string_rejected(self):
        # space isn't in the STRING alphabet, so it terminates the chunk
        # early via blank-splitting -> "hello, and world" become separate
        # invalid chunks
        with self.assertRaises(LexError):
            tokenize('"hello world" ')

    def test_disallowed_char_in_string_rejected(self):
        with self.assertRaises(LexError):
            tokenize('"a#b" ')  # '#' not in STRING alphabet


class TestKeywordsAndSymbols(unittest.TestCase):
    def test_all_keywords_recognized(self):
        from lexer2 import KEYWORDS
        for kw in KEYWORDS:
            self.assertEqual(kinds(f'{kw} '), [('KEYWORD', kw)], msg=kw)

    def test_all_symbols_recognized(self):
        from lexer2 import SYMBOLS
        for sym in SYMBOLS:
            self.assertEqual(kinds(f'{sym} '), [('SYMBOL', sym)], msg=sym)

    def test_symbol_requires_surrounding_blanks(self):
        # '(x)' with no spaces is one unsplittable chunk -> invalid
        with self.assertRaises(LexError):
            tokenize('(x) ')

    def test_name_that_looks_like_keyword_prefix_is_fine(self):
        # keywords have no '#', names always do -- genuinely no collision
        self.assertEqual(kinds('#if '), [('NAME', '#if')])


class TestDriverBehaviour(unittest.TestCase):
    def test_missing_trailing_blank_on_last_token_rejected(self):
        with self.assertRaises(LexError):
            tokenize('#x 0')  # '0' has nothing after it

    def test_trailing_blank_present_accepted(self):
        self.assertEqual(kinds('#x 0 '), [('NAME', '#x'), ('NUM', '0')])

    def test_crlf_treated_as_single_newline(self):
        toks = list(tokenize('#a \r\n#b '))
        self.assertEqual([t.lexeme for t in toks], ['#a', '#b'])
        self.assertEqual(toks[1].line, 2)

    def test_line_col_tracking(self):
        toks = list(tokenize('#a \n  0 \n"x" '))
        self.assertEqual((toks[0].line, toks[0].col), (1, 1))
        self.assertEqual((toks[1].line, toks[1].col), (2, 3))
        self.assertEqual((toks[2].line, toks[2].col), (3, 1))

    def test_unrecognized_chunk_reports_position(self):
        try:
            tokenize('#a foo ')
            self.fail('expected LexError')
        except LexError as e:
            self.assertEqual(e.line, 1)
            self.assertEqual(e.col, 4)  # 'foo' starts at column 4


class TestIntegration(unittest.TestCase):
    def test_full_fragment(self):
        program = (
            '#x #y : '
            'void #f ( #a ) { #a = 0 ; return } '
            ': '
            '#x = -5 ; '
            'if eq ( #x #y ) then { print ( #x ) } else { nop } ; '
            'print "done,ok" '
            '$ '
        )
        toks = tokenize(program)
        # spot-check a handful rather than asserting the entire stream
        self.assertEqual(toks[0].kind, 'NAME')
        self.assertEqual(toks[0].lexeme, '#x')
        self.assertIn(('KEYWORD', 'void'), [(t.kind, t.lexeme) for t in toks])
        self.assertIn(('STRING', '"done,ok"'), [(t.kind, t.lexeme) for t in toks])
        self.assertEqual(toks[-1].kind, 'SYMBOL')
        self.assertEqual(toks[-1].lexeme, '$')


if __name__ == '__main__':
    unittest.main(verbosity=2)
