# Team Members

- Shavir Vallabh u23718146
- Warona Moleboge u23770912
- Kundai Ndemera u23941996
- Siyabonga Sibiya u23976072

# SPL Front End

A lexer, parser and (optional) type analyser for the Students' Programming
Language (SPL), built for the COS 341 semester practical. Give it an SPL
program and it either writes the program's syntax tree to `tree.xml` or tells
you exactly what is wrong with it.

## Two ways to run it

You only need **Python 3.10 or later**. There is nothing to install. Run all
commands from the project folder.

| | **Option 1: GUI** | **Option 2: Command line** |
|---|---|---|
| Start it with | `python group_14_gui.py` | `python group_14_cli.py SPL.txt` |
| Best for | Trying programs out, seeing the tree, fixing errors | Producing `tree.xml` quickly, scripting |
| You get | A window with an editor, syntax tree view and error messages | `tree.xml` on disk, or an error message |

Both use the same lexer and parser and produce the same `tree.xml`.

### Option 1: the GUI

```bash
python group_14_gui.py              # starts with a built-in sample program
python group_14_gui.py SPL.txt      # opens and runs a file straight away
```

On Windows you can usually also double-click `group_14_gui.py`.

1. **Load a program.** Click **Open SPL file...** (Ctrl+O), or type/paste
   into the source pane on the left. The pane is editable.
2. **Run it.** Click **Run** (F5 or Ctrl+Enter). Opening a file runs it
   automatically.
3. **Read the result.**

   | Where | What you see |
   |---|---|
   | **Result** pane (bottom) | A green tick and the node count on success, or the error message and hint |
   | **SPL source** pane (left) | On an error, the bad line is highlighted and the cursor is put on the bad token |
   | **Syntax tree** tab | The tree, expandable. Each node shows its unique id as `[n]`. Tokens are green; empty (nullable) rules are grey with an epsilon |
   | **tree.xml** tab | The exact text that will be saved |

4. **Save the output.** Click **Save tree.xml...** (Ctrl+S). The button is
   enabled only after a successful parse, and the saved file is identical to
   what the command line produces.
5. **Fix and re-run.** Edit the source pane and press Run again.

Tick **Also run type analysis** to run the optional type checker after a
successful parse (the same as `--typecheck` on the command line). Type errors
are listed with their line numbers; the syntax tree is still produced.

Good to know:

- The Tab key types four spaces (a real tab character is a lexical error in SPL).
- Files must be plain ASCII.
- For very large programs the tree view shows only the first 6000 nodes. The
  **tree.xml** tab and the saved file are always complete.

### Option 2: the command line

```bash
python group_14_cli.py SPL.txt
```

This reads `SPL.txt` and, on success, writes `tree.xml` in the current
directory. Three more example programs are included (`SPL_simple.txt`,
`SPL_control.txt`, `SPL_functions.txt`), covering a plain program, branches
and loops, and function declarations.

```
python group_14_cli.py [source] [-o OUTPUT] [--typecheck]
```

| Argument | Meaning |
|---|---|
| `source` | Path to the SPL source file. Defaults to `SPL.txt` in the current directory. |
| `-o OUTPUT`, `--output OUTPUT` | Where to write the XML. Defaults to `tree.xml`. |
| `--typecheck` | After a successful parse, also run type analysis and report any type errors. |
| `-h`, `--help` | Show usage and exit. |

```bash
python group_14_cli.py                                   # read SPL.txt, write tree.xml
python group_14_cli.py my_program.txt -o output/tree.xml # explicit input and output
python group_14_cli.py SPL.txt --typecheck               # also run type checking
```

**Success** looks like this:

```
$ python group_14_cli.py SPL_simple.txt
Syntax OK. Syntax tree written to tree.xml
```

**Errors** are printed with the position and, where possible, a hint:

```
$ python group_14_cli.py broken.txt
Syntax error at line 4, col 6: unexpected ';'.
  Hint: Expected one of: NUM, USER-DEFINED-NAME, add, div, mod, mul, neg, sub

$ python group_14_cli.py lex.txt
Lexical error at line 4, col 7: unterminated string: '"hello' has no closing '"'. Hint: SPL strings cannot contain spaces (a space ends the token), so "hello world" is invalid - use e.g. "hello,world"

$ python group_14_cli.py prog.txt --typecheck
Syntax OK. Syntax tree written to tree.xml
TYPE ERROR (line 4): Assignment is not well-typed: target '#y' has type 'unknown', expected 'numeric'.
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Success. `tree.xml` was written (and, with `--typecheck`, the program is well-typed). |
| `1` | A lexical, syntax, or (with `--typecheck`) type error was found. The error is printed to stderr. For lexical and syntax errors no `tree.xml` is written, and a stale one from an earlier run is deleted. |
| `2` | The source file couldn't be read (missing file, permissions, or not plain ASCII). |

## The output: `tree.xml`

Every node of the syntax tree becomes one `<node>` element, listed in
pre-order (a parent always appears before its children). The fields present
depend on the kind of node, per the spec:

- **root** - `id`, `contents`, `children`
- **inner node** - `id`, `contents`, `children`, `parent`
- **leaf node** - `id`, `contents`, `parent` (no `children`)

`id` is a unique, tree-wide integer; `children` lists the `id`s of the node's
immediate children; `contents` is the grammar non-terminal for a root or inner
node, or the literal token text for a leaf. These `id`s are designed to later
double as foreign keys into a semantic data table for name-scope and type
analysis.

## Running the tests

```bash
pip install pytest
python test.py
```

This covers the lexer, the parser, the type analyser, an end-to-end pipeline
test (lexing, parsing, XML writing and type checking together), and the GUI.

(`python -m unittest discover -s tests -t .` also works, but only runs the
`unittest`-style tests, not the whole suite.)

## Setup notes

- **tkinter** (used only by the GUI) is included with the standard Python
  installers for Windows and macOS. On Debian/Ubuntu install it with
  `sudo apt install python3-tk`. The command-line program does not need it.
- No third-party packages are used anywhere in the program. `pytest` is only
  needed to run the tests.

## Project layout

```
group_14_cli.py              command-line entry point (Option 2)
group_14_gui.py           GUI entry point (Option 1)
spl_pipeline.py      lex -> parse -> XML (-> type check) as a function; used by the GUI
lexer/               tokenizer: SPL text -> list of tokens
parser/              SLR(1) parser: tokens -> syntax tree (see parser/grammar.py)
xmlwriter/           syntax tree -> tree.xml
semantics/           optional type analysis (--typecheck), built on the
                     syntax tree via semantics/cst_to_ast.py
tests/               unit tests for the above, plus the pipeline and GUI tests
SPL.txt, SPL_*.txt   example SPL programs
```
