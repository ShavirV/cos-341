import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lexer"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))

from lexer import tokenize, LexError
from parser import parse_tokens, SyntaxError_


def dump(node, indent=0):
    print("  " * indent + f"[{node.id}] {node.node_type}:{node.contents}")
    for c in node.children:
        dump(c, indent + 1)

# probably a valid program idk
VALID_PROGRAM = (
    '#x #y : '
    'num #square ( #n ) { : : return ( mul ( #n #n ) ) } '
    ': '
    '#x = #square ( 5 ) ; '
    'if larger ( #x 0 ) then { print ( #x ) ; } else { nop ; } ; '
    'while eq ( #y 0 ) do { #y = 1 ; } ; '
    '$ '
)

# Lexically valid but syntactically invalid: ASSIGN with a missing TERM.
BROKEN_ASSIGN = '#x : : : #x = ; $ '  # '=' with nothing after it


if __name__ == "__main__":
    print("=== Valid program ===")
    tokens = tokenize(VALID_PROGRAM)
    root = parse_tokens(tokens)
    dump(root)

    print("\n=== Invalid program (should raise a syntax error) ===")
    try:
        tokens = tokenize(BROKEN_ASSIGN)
        parse_tokens(tokens)
        print("ERROR: expected a SyntaxError_ but parsing succeeded")
    except SyntaxError_ as e:
        print("Got expected syntax error:")
        print(e)
    except LexError as e:
        print("Got a LexError instead (unexpected here):")
        print(e)
