"""
Generic syntax-tree node for SPL.

"""

from __future__ import annotations
from typing import List, Optional


# ---------------------------------------------------------------------------
# Grammar symbol / rule tags.
# For nonterminals that have exactly one production shape, the kind is just
# the nonterminal's name (e.g. "V_DECL_EPS", "V_DECL_CONS"). For terminals
# that carry a value (NAME, NUM, STRING) we store the literal text in
# node.value.
# ---------------------------------------------------------------------------

class Kind:
    SPL_PROG = "SPL_PROG"

    P = "P"

    V_DECL_EPS = "V_DECL_EPS"          # V_DECL -> epsilon
    V_DECL_CONS = "V_DECL_CONS"        # V_DECL -> NAME V_DECL

    F_DECL_EPS = "F_DECL_EPS"          # F_DECL -> epsilon
    F_DECL_CONS = "F_DECL_CONS"        # F_DECL -> F_TYPE F_DECL

    F_TYPE_VOID = "F_TYPE_VOID"        # F_TYPE -> void NAME ( V_DECL ) { P return }
    F_TYPE_NUM = "F_TYPE_NUM"          # F_TYPE -> num NAME ( V_DECL ) { P return ( TERM ) }

    ALGO_EPS = "ALGO_EPS"              # ALGO -> epsilon
    ALGO_CONS = "ALGO_CONS"            # ALGO -> INSTR ; ALGO

    OUTP_TERM = "OUTP_TERM"            # OUTP -> ( TERM )
    OUTP_STRING = "OUTP_STRING"        # OUTP -> STRING

    INSTR_PRINT = "INSTR_PRINT"        # INSTR -> print OUTP
    INSTR_NOP = "INSTR_NOP"            # INSTR -> nop
    INSTR_COMMENT = "INSTR_COMMENT"    # INSTR -> comment STRING
    INSTR_ASSIGN = "INSTR_ASSIGN"      # INSTR -> ASSIGN
    INSTR_BRANCH = "INSTR_BRANCH"      # INSTR -> BRANCH
    INSTR_LOOP = "INSTR_LOOP"          # INSTR -> LOOP
    INSTR_CALL = "INSTR_CALL"          # INSTR -> CALL

    CALL = "CALL"                      # CALL -> NAME ( INPUT )

    INPUT_EPS = "INPUT_EPS"            # INPUT -> epsilon
    INPUT_CONS = "INPUT_CONS"          # INPUT -> TERM INPUT

    ASSIGN = "ASSIGN"                  # ASSIGN -> NAME = TERM

    TERM_NAME = "TERM_NAME"            # TERM -> NAME
    TERM_NUM = "TERM_NUM"              # TERM -> NUM
    TERM_CALL = "TERM_CALL"            # TERM -> CALL
    TERM_MOD = "TERM_MOD"              # TERM -> mod ( TERM TERM )
    TERM_DIV = "TERM_DIV"              # TERM -> div ( TERM TERM )
    TERM_ADD = "TERM_ADD"              # TERM -> add ( TERM TERM )
    TERM_SUB = "TERM_SUB"              # TERM -> sub ( TERM TERM )
    TERM_MUL = "TERM_MUL"              # TERM -> mul ( TERM TERM )
    TERM_NEG = "TERM_NEG"              # TERM -> neg ( TERM )

    BRANCH = "BRANCH"                  # BRANCH -> if BOOL then { ALGO } else { ALGO }

    BOOL_NOT = "BOOL_NOT"              # BOOL -> not ( BOOL )
    BOOL_AND = "BOOL_AND"              # BOOL -> and ( BOOL BOOL )
    BOOL_OR = "BOOL_OR"                # BOOL -> or ( BOOL BOOL )
    BOOL_EQ = "BOOL_EQ"                # BOOL -> eq ( TERM TERM )
    BOOL_LARGER = "BOOL_LARGER"        # BOOL -> larger ( TERM TERM )
    BOOL_LESSER = "BOOL_LESSER"        # BOOL -> lesser ( TERM TERM )

    COND_WHILE = "COND_WHILE"          # COND -> while
    COND_UNTIL = "COND_UNTIL"          # COND -> until

    LOOP_PRE = "LOOP_PRE"              # LOOP -> COND BOOL do { ALGO }
    LOOP_POST = "LOOP_POST"            # LOOP -> do { ALGO } COND BOOL

    NAME = "NAME"                      # terminal, node.value = system-generated name
    NUM = "NUM"                        # terminal, node.value = literal text, e.g. "3" or "3.14"
    STRING = "STRING"                  # terminal, node.value = literal text


class Node:
    __slots__ = ("kind", "children", "value", "type", "line", "sym_id")

    def __init__(
        self,
        kind: str,
        children: Optional[List["Node"]] = None,
        value: Optional[str] = None,
        line: Optional[int] = None,
        sym_id: Optional[str] = None,
    ):
        self.kind = kind
        self.children = children or []
        self.value = value
        self.type = "unknown"          # every node starts "unknown" per the spec
        self.line = line
        # sym_id: the symbol-table key for NAME nodes (system-generated name
        # from phase 2a). Falls back to `value` if not separately supplied.
        self.sym_id = sym_id if sym_id is not None else value

    def __repr__(self):
        v = f" value={self.value!r}" if self.value is not None else ""
        return f"<{self.kind}{v} type={self.type}>"
