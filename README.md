# SPL Front End

Semester assignment for COS 341 (Compiler Construction) - a lexer, parser,
and (optional) type analyser for the Students' Programming Language (SPL),
per the practical's syntax specification.

Given an SPL source file, this program either:

- reports a lexical or syntax error and exits with a non-zero status, or
- writes the program's syntax tree to `tree.xml`.

`tree.xml` is the graded artifact - the tutors check that file, not the code
that produced it.

## Requirements

- Python 3.10 or later. No third-party packages are needed; only the
  standard library is used.

## Running it

From the repository root:

```bash
python main.py SPL.txt
```

This reads `SPL.txt`, and on success writes `tree.xml` in the current
directory. Three more example programs are included - `SPL_simple.txt`,
`SPL_control.txt`, `SPL_functions.txt` - covering a plain program, branches
and loops, and function declarations, respectively. Try any of them the same
way:

```bash
python main.py SPL_control.txt
```

### Command-line options

```
python main.py [source] [-o OUTPUT] [--typecheck]
```

| Argument | Meaning |
|---|---|
| `source` | Path to the SPL source file. Defaults to `SPL.txt` in the current directory. |
| `-o OUTPUT`, `--output OUTPUT` | Where to write the XML output. Defaults to `tree.xml`. |
| `--typecheck` | After a successful parse, also run type analysis and report any type errors. |
| `-h`, `--help` | Show usage and exit. |

Examples:

```bash
# Default: read SPL.txt, write tree.xml
python main.py

# Explicit input and output paths
python main.py my_program.txt -o output/tree.xml

# Also run type checking
python main.py SPL.txt --typecheck
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. `tree.xml` was written (and, with `--typecheck`, the program is well-typed). |
| `1` | A lexical, syntax, or (with `--typecheck`) type error was found. The error is printed to stderr; no `tree.xml` is written, and a stale one from an earlier run is deleted. |
| `2` | The source file couldn't be read (missing file, permissions, or the file isn't plain ASCII). |

### What "success" looks like

```
$ python main.py SPL_simple.txt
Syntax OK. Syntax tree written to tree.xml
```

### What an error looks like

```
$ python main.py broken.txt
Lexical error at line 1, col 1: 'bad$token' is not a keyword, symbol,
or a valid NUM / USER-DEFINED-NAME / STRING token
```

A syntax error additionally names the token position and lists what the
parser would have accepted there, for example:

```
Syntax error at line 3, col 9: unexpected ';'.
  Hint: Expected one of: (, NUM, USER-DEFINED-NAME, add, div, mod, mul, neg, sub
```

## The output: `tree.xml`

Every node of the syntax tree becomes one `<node>` element, listed in
pre-order (a parent always appears before its children). The fields present
depend on the kind of node, per the spec:

- **root** - `id`, `contents`, `children`
- **inner node** - `id`, `contents`, `children`, `parent`
- **leaf node** - `id`, `contents`, `parent` (no `children`)

`id` is a unique, tree-wide integer; `children` lists the `id`s of the
node's immediate children; `contents` is the grammar non-terminal for an
inner/root node, or the literal token text for a leaf. These `id`s are
designed to later double as foreign keys into a semantic data table for
name-scope and type analysis.

## Running the tests

```bash
python -m unittest discover -s tests -t .
```

This covers the lexer, the parser, the type analyser, and an end-to-end
pipeline test that runs a full program through lexing, parsing, XML
writing, and type checking together.

## Project layout

```
main.py             CLI entry point - the program described above
lexer/               tokenizer: SPL.txt -> List[Token]
parser/               SLR(1) parser: tokens -> syntax tree (see parser/grammar.py)
xmlwriter/            syntax tree -> tree.xml
semantics/            optional type analysis (--typecheck), built on the
                      syntax tree via semantics/cst_to_ast.py
tests/               unit tests for the above, plus the pipeline test
SPL.txt, SPL_*.txt   example SPL programs
```

## Design notes worth knowing

- **Blank-delimited tokenization.** Per the spec, every token must be
  followed by blank space (`' '`, `'\r'`, or `'\n'`); the lexer splits on
  blanks first, then classifies each chunk as a whole. The one exception is
  the end-of-program marker `$`, which may be the very last character in
  the file with no trailing blank after it.
- **SLR(1) parser.** The grammar's only ambiguity - a `USER-DEFINED-NAME`
  that could start a bare `TERM`, an `ASSIGN`, or a `CALL` - is resolved
  naturally by the shift/reduce parser rather than by extra lookahead; the
  grammar builds with zero shift/reduce or reduce/reduce conflicts.
- **Type analysis is optional and separate.** It isn't part of the graded
  syntax-phase output; it's included here as a head start on the next
  phase of the project, run only when `--typecheck` is passed.
