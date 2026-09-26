"""
Symbol table for phase 2b (Type Analysis).

This module stores:
    sys_name -> {"type": <"unknown"|"numeric"|"procedure"|...>, "kind": <"var"|"func">, "line": <int|None>}

and offers the small set of get/set operations the TypeAnalyzer needs.
"""

from __future__ import annotations
from typing import Dict, Optional


class SymbolTable:
    def __init__(self):
        self._table: Dict[str, dict] = {}

    def declare(self, sys_name: str, initial_type: str = "unknown",
                kind: Optional[str] = None, line: Optional[int] = None) -> None:
        if sys_name not in self._table:
            self._table[sys_name] = {"type": initial_type, "kind": kind, "line": line}

    def set_type(self, sys_name: str, new_type: str) -> None:
        if sys_name not in self._table:
            self._table[sys_name] = {"type": new_type, "kind": None, "line": None}
        else:
            self._table[sys_name]["type"] = new_type

    def set_declared_type(self, sys_name: str, new_type: str, line: Optional[int] = None) -> Optional[str]:
        
        entry = self._table.get(sys_name)
        if entry is None or entry.get("type") in (None, "unknown"):
            self._table[sys_name] = {
                "type": new_type,
                "kind": (entry or {}).get("kind"),
                "line": (entry or {}).get("line", line),
            }
            return None
        existing_type = entry["type"]
        if existing_type != new_type:
            # Conflict: don't overwrite. Keep the first-seen type so the
            # error is stable, and report it to the caller.
            return existing_type
        return None

    def get_type(self, sys_name: str) -> str:
        entry = self._table.get(sys_name)
        return entry["type"] if entry else "unknown"

    def has(self, sys_name: str) -> bool:
        return sys_name in self._table

    def dump(self) -> Dict[str, dict]:
        return dict(self._table)

    def __repr__(self):
        lines = [f"  {name}: {info}" for name, info in self._table.items()]
        return "SymbolTable{\n" + "\n".join(lines) + "\n}"
