import os
import re
import shutil
import subprocess
import tempfile
import unittest

from lexer.lexer import tokenize
from parser.parser import parse_tokens
from semantics.cst_to_ast import convert
from semantics.scope_analyzer import ScopeAnalyzer
from semantics.symbol_table import SymbolTable
from semantics.type_analyzer import TypeAnalyzer
from codegen.codegen import generate_program

HAS_GPP = shutil.which("g++") is not None


def gen(text):
    """SPL source -> generated C++ (runs the real front end first)."""
    ast = convert(parse_tokens(tokenize(text)))
    symtab = SymbolTable()
    assert ScopeAnalyzer(symtab).analyze(ast)
    ta = TypeAnalyzer(symtab)
    assert ta.analyze(ast, strict=False)
    return generate_program(ast, symtab, ta.number_type)


def run_cpp(code):
    """Compile the generated code with g++, run it, return what it printed."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "prog.cpp")
        exe = os.path.join(d, "prog.exe")
        with open(src, "w") as f:
            f.write(code)
        subprocess.run(["g++", src, "-o", exe], check=True, capture_output=True)
        return subprocess.run([exe], capture_output=True, text=True).stdout


SIMPLE = """#x #y :
:
print "hello" ;
#x = 5 ;
print "x,value:" ;
print ( #x ) ;
"""

ARITH = """#x #y :
:
#x = add ( 3 mul ( 2 4 ) ) ;
#y = neg ( #x ) ;
#x = -5 ;
comment "done" ;
nop ;
print ( #y ) ;
"""

CONTROL = """#i #n :
:
#n = 3 ;
#i = 0 ;
while larger ( #n #i ) do { print ( #i ) ; #i = add ( #i 1 ) ; } ;
if and ( lesser ( #i 10 ) not ( eq ( #i 0 ) ) ) then { print "big" ; } else { nop ; } ;
do { #i = sub ( #i 1 ) ; } until or ( eq ( #i 0 ) lesser ( #i 0 ) ) ;
print ( #i ) ;
"""

LOOPS = """#i :
:
#i = 5 ;
until eq ( #i 2 ) do { print ( #i ) ; #i = sub ( #i 1 ) ; } ;
do { print ( #i ) ; #i = add ( #i 1 ) ; } while lesser ( #i 4 ) ;
print ( #i ) ;
"""

FLOAT = """#x :
:
#x = div ( 7 2 ) ;
print ( #x ) ;
"""

FUNCTIONS = """#x #result :
num #add ( #a #b ) {
#tmp :
:
#tmp = add ( #a #b ) ;
return ( #tmp )
}
void #show ( #n ) {
:
:
print "number:" ;
print ( #n ) ;
return
}
:
#x = 7 ;
#result = #add ( #x 3 ) ;
#show ( #result ) ;
print "result:" ;
print ( #result ) ;
"""


class TestGeneratedText(unittest.TestCase):
    def test_print_string(self):
        self.assertIn('std::cout << "hello";', gen(SIMPLE))

    def test_nop_and_comment(self):
        code = gen(ARITH)
        self.assertIn("/* nop */", code)
        self.assertIn('/* "done" */', code)

    def test_negative_literal_uses_ascii_minus(self):
        self.assertIn("= -5;", gen(ARITH))

    def test_int_program_declares_int(self):
        code = gen(SIMPLE)
        self.assertIn("int v0;", code)
        self.assertNotIn("float", code)

    def test_div_program_declares_float(self):
        code = gen(FLOAT)
        self.assertIn("float v0;", code)
        self.assertNotIn("int v", code)

    def test_binary_operators(self):
        code = gen(ARITH)
        self.assertIn(" * ", code)
        self.assertIn(" + ", code)

    def test_labels_are_unique(self):
        labels = re.findall(r"^(L\d+):", gen(CONTROL), re.MULTILINE)
        self.assertTrue(labels)
        self.assertEqual(len(labels), len(set(labels)))

    def test_every_goto_target_exists(self):
        code = gen(CONTROL)
        defined = set(re.findall(r"^(L\d+):", code, re.MULTILINE))
        targets = set(re.findall(r"goto (L\d+);", code))
        self.assertTrue(targets <= defined)

    def test_temporaries_declared_once(self):
        names = re.findall(r"(?:int|float) (v\d+);", gen(CONTROL))
        self.assertEqual(len(names), len(set(names)))

    def test_ends_with_end_marker_per_algo(self):
        self.assertIn("/* end */", gen(SIMPLE))

    def test_function_calls_are_inlined(self):
        code = gen(FUNCTIONS)
        self.assertIn("/* call */", code)
        self.assertNotIn("TERM_CALL", code)


@unittest.skipUnless(HAS_GPP, "g++ not installed")
class TestRunsCorrectly(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(run_cpp(gen(SIMPLE)), "hellox,value:5")

    def test_arithmetic(self):
        # y = neg(3 + 2*4) = -11
        self.assertEqual(run_cpp(gen(ARITH)), "-11")

    def test_while_if_and_not_do_until_or(self):
        self.assertEqual(run_cpp(gen(CONTROL)), "012big0")

    def test_until_and_do_while(self):
        self.assertEqual(run_cpp(gen(LOOPS)), "543234")

    def test_float_division(self):
        self.assertEqual(run_cpp(gen(FLOAT)), "3.5")

    def test_numeric_and_void_function_calls(self):
        self.assertEqual(run_cpp(gen(FUNCTIONS)), "number:10result:10")


NESTED_SAME_CALL = """#r :
num #sub3 ( #a #b #c ) {
:
:
return ( sub ( #a sub ( #b #c ) ) )
}
:
#r = #sub3 ( 100 #sub3 ( 50 20 5 ) 1 ) ;
print ( #r ) ;
"""

LABELS_TWICE = """#a #z :
num #count ( #n ) {
#s :
:
#s = 0 ;
while larger ( #n 0 ) do { #n = sub ( #n 1 ) ; #s = add ( #s 2 ) ; } ;
return ( #s )
}
:
#a = #count ( 3 ) ;
#z = #count ( #a ) ;
print ( #z ) ;
"""

SUBFUNCTION = """#r :
num #f ( #x ) {
:
num #g ( #y ) {
:
:
return ( mul ( #y 2 ) )
}
:
return ( add ( #g ( #x ) 1 ) )
}
:
#r = add ( #f ( 4 ) #f ( 5 ) ) ;
print ( #r ) ;
"""


class TestSpec3b(unittest.TestCase):
    def test_program_layout(self):
        code = gen(FUNCTIONS)
        order = [code.index(m) for m in (
            "begin of the non-executable code-mine", "end of the non-executable code-mine",
            "begin of executable C code", "#include <iostream>", "int main()",
            "return 0;", "end of executable C")]
        self.assertEqual(order, sorted(order))

    def test_code_mine_is_one_well_formed_comment(self):
        code = gen(FUNCTIONS)
        mine = code[code.index("/*\n"):code.index("/* end of the non-executable")]
        self.assertEqual(mine.count("/*"), 1)
        self.assertEqual(mine.count("*/"), 1)

    @unittest.skipUnless(HAS_GPP, "g++ not installed")
    def test_nested_call_of_same_function_in_arguments(self):
        self.assertEqual(run_cpp(gen(NESTED_SAME_CALL)), "66")

    @unittest.skipUnless(HAS_GPP, "g++ not installed")
    def test_labels_renamed_for_each_inlining(self):
        code = gen(LABELS_TWICE)
        labels = re.findall(r"^(L\d+):", code, re.MULTILINE)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(run_cpp(code), "12")

    @unittest.skipUnless(HAS_GPP, "g++ not installed")
    def test_subfunction_inlined_inside_function(self):
        self.assertEqual(run_cpp(gen(SUBFUNCTION)), "20")

    def test_wrong_argument_count_is_a_type_error(self):
        from spl_pipeline import analyze
        r = analyze("#x :\nnum #f ( #a ) { : : return ( #a ) }\n:\n#x = #f ( 1 2 ) ;\n", codegen=True)
        self.assertEqual([p.kind for p in r.problems], ["type"])
        self.assertEqual(r.code, "")

    def test_pipeline_generates_code_and_long_programs_work(self):
        from spl_pipeline import analyze
        r = analyze("#x :\n:\n" + "#x = add ( #x 1 ) ;\n" * 3000, codegen=True)
        self.assertEqual(r.problems, [])
        self.assertIn("int main()", r.code)



if __name__ == "__main__":
    unittest.main()