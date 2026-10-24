"""Quick harness: SPL text -> lex -> parse -> AST -> type analysis.
No 2a renamer here, so sym_id is the raw '#name' (fine for test programs
without shadowing or reused names)."""
import sys
from lexer.lexer import tokenize
from parser.parser import parse_tokens
from semantics.cst_to_ast import convert
from semantics.type_analyzer import TypeAnalyzer


def run(src):
    ast = convert(parse_tokens(tokenize(src)))
    ta = TypeAnalyzer()
    ok = ta.analyze(ast, strict=False)
    return ok, ta


CASES = {
    "valid: SPL.txt": (open("SPL.txt").read(), True),
    "valid: SPL_control.txt": (open("SPL_control.txt").read(), True),
    "valid: SPL_simple.txt": (open("SPL_simple.txt").read(), True),
    "valid: mod, ints only": ("#x\n:\n:\n#x = mod ( 7 2 ) ;\nprint ( #x ) ;\n", True),
    "valid: div with floats": ("#x\n:\n:\n#x = div ( 7.5 2 ) ;\n", True),
    "mod + div": ("#x\n:\n:\n#x = mod ( 7 2 ) ;\n#x = div ( 7 2 ) ;\n", False),
    "mod + decimal": ("#x\n:\n:\n#x = mod ( 7 2 ) ;\n#x = 2.5 ;\n", False),
    "undeclared deep in expr": ("#x\n:\n:\n#x = add ( mul ( #z 2 ) 1 ) ;\n", False),
    "void fn as TERM": ("#x\n:\nvoid #p ( ) {\n:\n:\nnop ;\nreturn\n}\n:\n#x = #p ( ) ;\n", False),
    "num fn as INSTR": ("#x\n:\nnum #f ( ) {\n:\n:\nreturn ( 1 )\n}\n:\n#f ( ) ;\n", False),
    "bad body, then called": ("#x\n:\nnum #f ( ) {\n:\n:\nreturn ( #q )\n}\n:\n#x = #f ( ) ;\n", False),
    "error inside if-branch": ("#x\n:\n:\nif eq ( #x 1 ) then {\n#x = #zz ;\n} else {\nnop ;\n} ;\n", False),
}

if __name__ == "__main__":
    bad = 0
    for name, (src, expect_ok) in CASES.items():
        ok, ta = run(src)
        status = "PASS" if ok == expect_ok else "FAIL"
        bad += status == "FAIL"
        nt = getattr(ta, "number_type", "-")
        print(f"[{status}] {name}: ok={ok} errors={len(ta.errors)} number_type={nt}")
        for e in ta.errors:
            print("       ", e)
    sys.exit(1 if bad else 0)
