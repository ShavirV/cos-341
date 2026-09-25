# SPL Lexer — Handoff Notes

For whoever's picking this up to build the parser. Read this before you touch
`lexer2.py` — it'll save you re-deriving decisions that were already argued
through.

## 1. The public interface (this is all the parser needs to know)

```python
from lexer2 import tokenize, Token, LexError

tokens = tokenize(source_text)   # returns List[Token], or raises LexError
```

**`Token`** — one per lexeme, in source order:
```python
Token(kind: str, lexeme: str, line: int, col: int)
```

**`kind`** is one of: `'KEYWORD'`, `'SYMBOL'`, `'NUM'`, `'NAME'`, `'STRING'`.
There is no separate token for end-of-file — the grammar's `$` is just the
last `SYMBOL` token in the stream, like any other. The parser should expect
to see it and treat it as the `$` in `SPL_PROG → P$`.

**`LexError`** — raised on any lexical failure, with `.line`, `.col`, and a
human-readable message already baked into `str(e)`. The parser doesn't need
to catch this mid-parse; if `tokenize()` succeeds, the entire input is
lexically valid — you get a clean list of tokens or nothing at all. There's
no partial/recovery mode.

**`KEYWORDS`** and **`SYMBOLS`** (sets, importable from `lexer2`) are the
exact literal strings the grammar treats as keywords/symbols — useful if the
parser wants to sanity-check a token's lexeme against `SYMBOLS`/`KEYWORDS`
rather than hardcoding strings again.

## 2. Design decisions worth knowing (not obvious from reading the code cold)

- **Tokenization is blank-delimited, not maximal-munch.** The spec requires
  every token to be followed by blank_space, so the driver splits the input
  on blanks first, then classifies each whole chunk. A chunk is a valid
  token iff exactly one of {keyword, symbol, NUM, NAME, STRING} matches it
  *entirely* — no partial matches, no backtracking. This means the DFAs for
  NUM/NAME/STRING are used as whole-string acceptors, not run inline
  character-by-character against the raw source.

- **Symbols (`( ) { } : ; = $`) are NOT exempt from the blank rule.**
  `( x )` is required; `(x)` is a lex error (the whole chunk `"(x)"` doesn't
  match anything). If your test SPL programs are copy-pasted from somewhere
  that doesn't space out parens, they'll fail here — that's intentional,
  per a literal reading of the spec.

- **The final token in the file must also be followed by blank_space.**
  Toggle: `REQUIRE_TRAILING_BLANK_AFTER_LAST_TOKEN` in `lexer2.py`. Currently
  `True`. If your tutor confirms EOF-right-after-`$` is fine, flip this.

- **`\n` is treated as blank_space alongside the spec's ASCII 32/13.**
  Spec only lists space and `\r`. We added `\n` pragmatically (Unix files
  have no `\r` at all; Windows `\r\n` is handled as one newline unit, not
  double-counted). Flagged here because it's a deviation from the literal
  spec text, not because it's expected to cause problems.

- **`STRING` literals cannot contain spaces.** The grammar's STRING
  alphabet is `(,|.|:|–|?|!|0-9|a-z)` — no space. So `"hello world"` is
  invalid; `"hello,world"` is fine. This is a direct reading of the given
  regex, not an implementation choice, but it's easy to forget when writing
  test SPL programs.

- **`NAME` and `KEYWORD` never collide**, by grammar design — every `NAME`
  starts with `#`, no keyword does. So there's no ambiguity to resolve at
  the lexer level; `#if` is a valid NAME, not the keyword `if`.

## 3. The NUM DFA — the one non-trivial automaton here

7 states: `A` (start) → `D` (after `-`) / `C` (bare `0`, final) / `B`
(nonzero digits, final) → `Z` (signed zero, **not** final) → `GH`
(post-`.`, ends in 0 so far, **not** final) ⇄ `I` (post-`.`, ends in
non-zero, final).

The two traps that ate real time during design, in case similar bugs show
up elsewhere:
- **`C` and `Z` must stay separate states**, even though both represent
  "just saw a 0." `0` alone is valid (rule 1); `-0` alone is not (no rule
  permits a signed zero with nothing after it) — only `-0.x` is (rule 2).
  Collapsing these two into one state is the classic bug here.
- **No self-loop on `-`.** `(–|ε)` in the regex means *at most one* minus,
  not zero-or-more.

If the parser layer ever needs to inspect a `NUM` lexeme's structure
(e.g. splitting sign/integer/fraction parts for semantic analysis later),
the state names in `run_num()` inside `lexer2.py` map directly onto this.

## 4. What's already tested (don't re-derive from scratch)

`test_lexer.py` has 40 tests, organized as:
- **Transition coverage** — one test per arrow in each DFA's state diagram
  (13 for NUM, 2 for NAME, 3 for STRING). If you add a grammar rule that
  touches these lexical categories, extend this file the same way: draw
  the diagram, write one test per edge.
- **Boundary/negative cases** — the specific bugs found during design
  (`-0`, `00`, `5.`, `--5`, `0.10`, etc.), each asserting *rejection*.
- **Driver-level tests** — blank-splitting, line/col tracking, CRLF,
  trailing-blank enforcement.
- **One integration test** — a full tokenizable SPL fragment, spot-checked
  rather than exhaustively asserted.

Run with `python3 -m unittest test_lexer.py -v`. All 40 currently pass.

**Not yet tested:** a real `SPL.txt`-shaped program exercising every grammar
rule end to end (both `F_TYPE` forms, both `LOOP` forms, nested `TERM`s).
Worth building once the parser exists, since it'll be the shared fixture
for both layers.

## 5. Known open question for the tutor

Whether `REQUIRE_TRAILING_BLANK_AFTER_LAST_TOKEN` should really apply to the
very last token in the file (strict spec reading) or whether EOF right after
`$` is acceptable in practice. Doesn't block parser work either way — just
flag it if grading feedback ever comes back confused about a trailing-space
requirement on the last line of a test file.
