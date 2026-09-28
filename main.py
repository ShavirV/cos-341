"""
SPL front end.

    python main.py [SPL.txt] [-o tree.xml] [--typecheck]

1. lex  SPL.txt            -> tokens          (LexError on bad tokens)
2. parse tokens            -> syntax tree     (SyntaxError_ on bad syntax)
3. write tree.xml                             (the graded output of this phase)
4. --typecheck (optional)  -> type analysis   (all type errors are reported)

Exit code: 0 = success, 1 = lexical/syntax/type error, 2 = file problem.
"""

import argparse
import os
import sys

from lexer.lexer import tokenize, LexError
from parser.parser import parse_tokens, SyntaxError_
from xmlwriter.node import NodeIDGenerator
from xmlwriter.xmlwriter import write_tree


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SPL lexer + parser (+ optional type analysis)")
    ap.add_argument("source", nargs="?", default="SPL.txt", help="input file (default: SPL.txt)")
    ap.add_argument("-o", "--output", default="tree.xml", help="output XML file (default: tree.xml)")
    ap.add_argument("--typecheck", action="store_true", help="also run type analysis after parsing")
    args = ap.parse_args(argv)

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

    if args.typecheck:
        from semantics.cst_to_ast import convert
        from semantics.type_analyzer import TypeAnalyzer

        analyzer = TypeAnalyzer()
        ok = analyzer.analyze(convert(tree), strict=False)
        if not ok:
            for err in analyzer.errors:
                print(err, file=sys.stderr)
            return 1
        print("Type analysis OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
