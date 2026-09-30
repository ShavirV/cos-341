"""
GUI-independent driver for the SPL front end.

analyze(text) runs the same stages as main.py (lex -> parse -> XML, and
optionally type analysis) but returns a Result object instead of printing and
exiting, so the GUI (spl_gui.py) and the tests can use it without a display.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from lexer.lexer import tokenize, LexError
from parser.parser import parse_tokens, SyntaxError_
from xmlwriter.node import Node, NodeIDGenerator
from xmlwriter.xmlwriter import tree_to_xml


@dataclass
class Problem:
    kind: str                     # "lexical" | "syntax" | "type" | "internal"
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

    @property
    def syntax_ok(self) -> bool:
        return self.tree is not None

    @property
    def ok(self) -> bool:
        """No problems at all (and, if type checking was requested, it passed)."""
        return self.syntax_ok and not self.problems


def analyze(text: str, typecheck: bool = False) -> Result:
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

    if typecheck:
        result.type_checked = True
        try:
            # imported lazily, like main.py, so plain parsing never depends on it
            from semantics.cst_to_ast import convert
            from semantics.type_analyzer import TypeAnalyzer

            analyzer = TypeAnalyzer()
            if not analyzer.analyze(convert(tree), strict=False):
                for err in analyzer.errors:
                    result.problems.append(Problem("type", err.message, err.line))
        except RecursionError:
            result.problems.append(
                Problem("internal", "Program is too long/deeply nested for type analysis."))
        except Exception as e:
            result.problems.append(Problem("internal", f"Type analysis crashed: {type(e).__name__}: {e}"))
    return result
