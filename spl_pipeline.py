"""
GUI-independent driver for the SPL front end.

analyze(text) runs the same stages as the CLI (lex -> parse -> XML, and
optionally scope analysis (phase 2a) and type analysis (phase 2b)) but returns a Result object instead of printing and
exiting, so the GUI (spl_gui.py) and the tests can use it without a display.
"""

import sys
from dataclasses import dataclass, field
from typing import List, Optional

from lexer.lexer import tokenize, LexError
from parser.parser import parse_tokens, SyntaxError_
from xmlwriter.node import Node, NodeIDGenerator
from xmlwriter.xmlwriter import tree_to_xml


# the tree walks are recursive (one level per instruction), so long programs
# need more head-room than Python's default limit of 1000 frames
sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))


@dataclass
class Problem:
    kind: str                     # "lexical" | "syntax" | "scope" | "type" | "internal"
    message: str
    line: Optional[int] = None    # 1-based, when known
    col: Optional[int] = None


@dataclass
class Result:
    tree: Optional[Node] = None   # syntax tree; set iff lexing + parsing succeeded
    xml: str = ""                 # contents of tree.xml; set iff tree is set
    node_count: int = 0           # number of nodes in the syntax tree
    problems: List[Problem] = field(default_factory=list)
    type_checked: bool = False    # was type analysis requested (and reached)?
    scope_checked: bool = False   # was scope analysis requested (and reached)?
    symtab: Optional[object] = None   # SymbolTable (renamed names), set if scope analysis ran
    ast: Optional[object] = None      # abstract tree (names renamed), set if scope analysis ran
    number_type: Optional[str] = None # "int" / "float", set if type analysis ran
    code: str = ""                    # generated C++ (only if analyze(..., codegen=True) succeeded)

    @property
    def syntax_ok(self) -> bool:
        return self.tree is not None

    @property
    def ok(self) -> bool:
        """No problems at all (and, if type checking was requested, it passed)."""
        return self.syntax_ok and not self.problems


def analyze(text: str, typecheck: bool = False, scopecheck: bool = False,
            codegen: bool = False) -> Result:
    """typecheck=True implies scopecheck: type analysis needs the unique internal
    names from phase 2a. codegen=True implies both and, if the program is
    error-free, also fills Result.code (phases 3a/3b). If scope errors are found, type analysis is skipped
    (it would only report follow-up errors for the same undeclared names)."""
    if codegen:
        typecheck = True
    result = Result()
    NodeIDGenerator.reset()

    try:
        tree = parse_tokens(tokenize(text))
    except LexError as e:
        result.problems.append(Problem("lexical", str(e), e.line, e.col))
        return result
    except SyntaxError_ as e:
        result.problems.append(Problem("syntax", str(e), e.line, e.col))
        return result
    except RecursionError:
        result.problems.append(Problem("internal", "Program is too deeply nested to process."))
        return result
    except Exception as e:  # a bug in a stage must not kill the GUI
        result.problems.append(Problem("internal", f"{type(e).__name__}: {e}"))
        return result

    result.tree = tree
    result.xml = tree_to_xml(tree)
    stack, n = [tree], 0
    while stack:
        node = stack.pop()
        n += 1
        stack.extend(node.children)
    result.node_count = n

    if typecheck or scopecheck:
        try:
            # imported lazily, like the CLI, so plain parsing never depends on them
            from semantics.cst_to_ast import convert
            from semantics.scope_analyzer import ScopeAnalyzer
            from semantics.symbol_table import SymbolTable

            ast = convert(tree)
            symtab = SymbolTable()
            result.scope_checked = True
            sa = ScopeAnalyzer(symtab)
            scope_ok = sa.analyze(ast)
            result.symtab = symtab
            result.ast = ast
            for err in sa.errors:
                result.problems.append(Problem("scope", err.message, err.line))

            if typecheck and scope_ok:
                from semantics.type_analyzer import TypeAnalyzer

                result.type_checked = True
                analyzer = TypeAnalyzer(symtab)
                if not analyzer.analyze(ast, strict=False):
                    for err in analyzer.errors:
                        result.problems.append(Problem("type", err.message, err.line))
                else:
                    result.number_type = analyzer.number_type
                    if codegen:
                        from codegen.codegen import generate_program

                        result.code = generate_program(ast, symtab, analyzer.number_type)
        except RecursionError:
            result.problems.append(
                Problem("internal", "Program is too long/deeply nested for semantic analysis."))
        except Exception as e:
            result.problems.append(Problem("internal", f"Semantic analysis crashed: {type(e).__name__}: {e}"))
    return result
