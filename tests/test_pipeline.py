"""
End-to-end tests: source text -> lexer -> parser -> tree.xml / type analysis.

The other test files exercise each stage in isolation (the type-analyzer tests
even build their trees by hand). These make sure the stages actually fit together.
"""

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from lexer.lexer import tokenize
from parser.parser import parse_tokens
from semantics.cst_to_ast import convert
from semantics.type_analyzer import TypeAnalyzer, OK
from xmlwriter.node import NodeIDGenerator
from xmlwriter.xmlwriter import tree_to_xml

REPO = Path(__file__).resolve().parent.parent

# Uses both F_TYPE forms, both LOOP forms, calls (statement + term), branch,
# print of term and string, comment, nested arithmetic and a decimal NUM.
FULL_PROGRAM = (
    '#x #y : '
    'num #square ( #n ) { : : return ( mul ( #n #n ) ) } '
    'void #hello ( ) { : : print "hi,there" ; return } '
    ': '
    '#x = #square ( 5 ) ; '
    '#hello ( ) ; '
    'if larger ( #x 0 ) then { print ( #x ) ; } else { nop ; } ; '
    'while eq ( #y 0 ) do { #y = 1 ; } ; '
    'do { #y = add ( #y 0.5 ) ; } until larger ( #y 3 ) ; '
    'comment "done" ; '
)


def parse(src):
    NodeIDGenerator.reset()
    return parse_tokens(tokenize(src))


def typecheck(src):
    ta = TypeAnalyzer()
    ok = ta.analyze(convert(parse(src)), strict=False)
    return ok, [e.message for e in ta.errors]


# ---------------------------------------------------------------- tree.xml

def test_xml_is_well_formed_and_ids_are_consistent():
    root = parse(FULL_PROGRAM)
    nodes = ET.fromstring(tree_to_xml(root)).findall("node")

    ids = [n.findtext("id") for n in nodes]
    assert len(ids) == len(set(ids)), "node ids must be unique"

    by_id = {n.findtext("id"): n for n in nodes}
    roots = [n for n in nodes if n.find("parent") is None]
    assert len(roots) == 1 and roots[0].findtext("contents") == "SPL_PROG"

    for n in nodes:
        if n.find("children") is None:
            assert n.find("parent") is not None      # leaf
            continue
        for c in n.find("children").findall("child"):
            # every child listed by a parent must point back at that parent
            assert by_id[c.text].findtext("parent") == n.findtext("id")


def test_deep_tree_does_not_hit_recursion_limit():
    # ALGO nests once per statement, so this tree is ~3000 levels deep
    src = ": : " + "nop ; " * 3000
    ET.fromstring(tree_to_xml(parse(src)))


def test_xml_escapes_special_characters():
    # STRING literals can contain '?', '!', ':' etc; make sure the XML stays valid
    xml = tree_to_xml(parse(': : print "a?b!c:d" ; '))
    ET.fromstring(xml)
    assert '"a?b!c:d"' in xml


# ------------------------------------------------------ parser -> analyzer

def test_full_program_parses_and_type_checks():
    ok, errors = typecheck(FULL_PROGRAM)
    assert ok, errors


def test_converter_output_has_analyzer_shape():
    ast = convert(parse(FULL_PROGRAM))
    assert ast.kind == "SPL_PROG" and len(ast.children) == 1
    p = ast.children[0]
    assert [c.kind for c in p.children][0] == "V_DECL_CONS"
    f_kinds = []
    node = p.children[1]
    while node.kind == "F_DECL_CONS":
        f_kinds.append(node.children[0].kind)
        node = node.children[1]
    assert f_kinds == ["F_TYPE_NUM", "F_TYPE_VOID"]


def test_type_errors_from_real_source_carry_line_numbers():
    src = ": :\n#ghost = 1 ;\n "
    ta = TypeAnalyzer()
    ta.analyze(convert(parse(src)), strict=False)
    assert len(ta.errors) == 1
    assert ta.errors[0].line == 2 and "#ghost" in ta.errors[0].message


def test_void_call_used_as_value_is_rejected():
    ok, errors = typecheck('#x : void #f ( ) { : : nop ; return } : #x = #f ( ) ; ')
    assert not ok and any("'void'" in e for e in errors)


def test_num_call_used_as_statement_is_rejected():
    ok, errors = typecheck(': num #f ( ) { : : return ( 1 ) } : #f ( ) ; ')
    assert not ok and any("'void' (procedure)" in e for e in errors)


def test_mod_and_div_together_rejected():
    ok, errors = typecheck('#x : : #x = mod ( 5 2 ) ; #x = div ( 4 2 ) ; ')
    assert not ok and "float-integer-conflict" in errors[0]


def test_num_function_may_call_an_earlier_function():
    ok, errors = typecheck(
        ': num #g ( ) { : : return ( 1 ) } '
        'num #f ( ) { : : return ( #g ( ) ) } : '
    )
    assert ok, errors


# --------------------------------------------------------------------- CLI

def _run_main(tmp_path, source, *flags):
    src = tmp_path / "SPL.txt"
    out = tmp_path / "tree.xml"
    src.write_text(source)
    proc = subprocess.run(
        [sys.executable, str(REPO / "main.py"), str(src), "-o", str(out), *flags],
        capture_output=True, text=True, cwd=REPO,
    )
    return proc, out


def test_cli_success_writes_tree(tmp_path):
    proc, out = _run_main(tmp_path, FULL_PROGRAM, "--typecheck")
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    ET.parse(out)


def test_cli_syntax_error_writes_no_tree(tmp_path):
    proc, out = _run_main(tmp_path, "#x : : #x = ; ")
    assert proc.returncode == 1
    assert "Syntax error" in proc.stderr and "Hint" in proc.stderr
    assert not out.exists()


def test_cli_lex_error_removes_stale_tree(tmp_path):
    (tmp_path / "tree.xml").write_text("stale")
    proc, out = _run_main(tmp_path, "#x : : #x = 05 ; ")
    assert proc.returncode == 1 and "Lexical error" in proc.stderr
    assert not out.exists()


def test_cli_type_error_exit_code(tmp_path):
    proc, _ = _run_main(tmp_path, ": :\n#ghost = 1 ;\n ", "--typecheck")
    assert proc.returncode == 1 and "TYPE ERROR (line 2)" in proc.stderr