"""
Error handling for SPL type analysis.

We collect ALL type errors found during a full tree walk (rather than
stopping at the first one) because that is far more useful to a compiler
user than a single failure. 

"""

from __future__ import annotations
from typing import List, Optional


class SPLTypeError:
    def __init__(self, message: str, line: Optional[int] = None, node=None):
        self.message = message
        self.line = line
        self.node = node

    def __str__(self):
        loc = f" (line {self.line})" if self.line is not None else ""
        return f"TYPE ERROR{loc}: {self.message}"

    def __repr__(self):
        return str(self)


class SPLTypeAnalysisFailed(Exception):
    """Raised by analyze() (strict mode) when one or more type errors were found."""

    def __init__(self, errors: List[SPLTypeError]):
        self.errors = errors
        msg = "\n".join(str(e) for e in errors)
        super().__init__(f"SPL type analysis failed with {len(errors)} error(s):\n{msg}")
