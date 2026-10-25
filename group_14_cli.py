"""
SPL front end.

    python group_14_cli.py [SPL.txt] [-o tree.xml] [--scope] [--typecheck] [--symtab] [--codegen] [-c OUT.cpp]

1. lex  SPL.txt            -> tokens          (LexError on bad tokens)
2. parse tokens            -> syntax tree     (SyntaxError_ on bad syntax)
3. write tree.xml                             (the graded output of this phase)
4. --scope     (optional)  -> scope analysis  (phase 2a: declarations, hierarchic calls,
                                               unique renaming; all errors are reported)
5. --typecheck (optional)  -> type analysis   (phase 2b; implies --scope, and is skipped
                                               if scope errors were found)

6. --codegen   (optional)  -> code generation (phases 3a/3b: C++ with inlined functions,
                                               written to out.cpp; implies --typecheck)

Exit code: 0 = success, 1 = lexical/syntax/type error, 2 = file problem.
"""

import argparse
import os
import sys

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

from lexer.lexer import tokenize, LexError
from parser.parser import parse_tokens, SyntaxError_
from xmlwriter.node import NodeIDGenerator
from xmlwriter.xmlwriter import write_tree


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SPL lexer + parser (+ optional type analysis)")
    ap.add_argument("source", nargs="?", default="SPL.txt", help="input file (default: SPL.txt)")
    ap.add_argument("-o", "--output", default="tree.xml", help="output XML file (default: tree.xml)")
    ap.add_argument("--scope", action="store_true",
                    help="also run scope analysis (declarations, hierarchic calls, unique renaming)")
    ap.add_argument("--typecheck", action="store_true",
                    help="also run type analysis after parsing (implies --scope)")
    ap.add_argument("--symtab", action="store_true",
                    help="print the symbol table (internal names) after successful analysis (implies --scope)")
    ap.add_argument("--codegen", action="store_true",
                    help="also generate executable C++ (implies --typecheck)")
    ap.add_argument("-c", "--code-output", default="out.cpp",
                    help="where to write the generated code (default: out.cpp)")
    args = ap.parse_args(argv)
    if args.codegen:
        args.typecheck = True

    try:
        with open(args.source, encoding="ascii", newline="") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Cannot read {args.source}: {e}", file=sys.stderr)
        return 2

    NodeIDGenerator.reset()
    try:
        tree = parse_tokens(tokenize(text))
    except (LexError, SyntaxError_) as e:
        # don't leave a stale tree.xml from an earlier run lying around
        if os.path.exists(args.output):
            os.remove(args.output)
        print(e, file=sys.stderr)
        return 1

    write_tree(tree, args.output)
    print(f"Syntax OK. Syntax tree written to {args.output}")

    if args.typecheck or args.scope or args.symtab:
        from semantics.cst_to_ast import convert
        from semantics.scope_analyzer import ScopeAnalyzer
        from semantics.symbol_table import SymbolTable

        ast = convert(tree)
        symtab = SymbolTable()
        scoper = ScopeAnalyzer(symtab)
        if not scoper.analyze(ast):
            for err in scoper.errors:
                print(err, file=sys.stderr)
            return 1
        print("Scope analysis OK.")

        if args.typecheck:
            from semantics.type_analyzer import TypeAnalyzer

            analyzer = TypeAnalyzer(symtab)
            if not analyzer.analyze(ast, strict=False):
                for err in analyzer.errors:
                    print(err, file=sys.stderr)
                return 1
            print("Type analysis OK.")

        if args.codegen:
            from codegen.codegen import generate_program

            try:
                code = generate_program(ast, symtab, analyzer.number_type)
            except (ValueError, NotImplementedError) as e:
                print(f"Code generation error: {e}", file=sys.stderr)
                return 1
            with open(args.code_output, "w", encoding="ascii", newline="\n") as f:
                f.write(code)
            print(f"Code generation OK. C++ written to {args.code_output}")

        if args.symtab:
            print(f"{'new name':<10}{'original':<14}{'kind':<6}{'level':<7}{'type':<11}line")
            for name, e in sorted(symtab.dump().items(), key=lambda kv: int(kv[0][3:])):
                print(f"{name:<10}{e.get('orig_name') or '':<14}{e.get('kind') or '':<6}"
                      f"{e.get('scope_level', ''):<7}{e.get('type'):<11}{e.get('line') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
