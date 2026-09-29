"""
Bridge between the parser and the type analyzer.

The parser produces a *concrete* syntax tree (xmlwriter.node.Node) 
one inner node per grammar rule, and a leaf for every terminal

The type analyzer works on an *abstract* tree (semantics.ast_nodes.Node) 
in which every production has its own Kind (V_DECL_EPS vs V_DECL_CONS, TERM_ADD
vs TERM_MUL, ...) and punctuation/keywords are dropped, so each rule handler
just sees the meaningful children, e.g. F_TYPE_NUM -> [NAME, V_DECL, P, TERM]

convert() turns the first into the second. It relies only on the shape of the
grammar, so a tree the parser accepted always converts cleanly

"""

from __future__ import annotations
from typing import Optional

from xmlwriter.node import Node as CSTNode
from semantics.ast_nodes import Node, Kind

_TERM_OPS = {
    "mod": Kind.TERM_MOD, "add": Kind.TERM_ADD, "sub": Kind.TERM_SUB,
    "mul": Kind.TERM_MUL, "div": Kind.TERM_DIV, "neg": Kind.TERM_NEG,
}
_BOOL_OPS = {
    "not": Kind.BOOL_NOT, "and": Kind.BOOL_AND, "or": Kind.BOOL_OR,
    "eq": Kind.BOOL_EQ, "larger": Kind.BOOL_LARGER, "lesser": Kind.BOOL_LESSER,
}


class ConversionError(Exception):
    """Raised if the concrete tree does not have the shape the grammar implies."""


def _first_line(n: CSTNode) -> Optional[int]:
    """Line of the first token underneath n (inner nodes have no line of their own)."""
    stack = [n]
    while stack:
        cur = stack.pop()
        if cur.is_leaf():
            if cur.line is not None:
                return cur.line
        else:
            stack.extend(reversed(cur.children))
    return None


def _terminal(n: CSTNode, kind: str) -> Node:
    return Node(kind, value=n.contents, line=n.line, sym_id=n.contents if kind == Kind.NAME else None)


def _nt(n: CSTNode, name: str) -> CSTNode:
    if n.node_type == "leaf" or n.contents != name:
        raise ConversionError(f"expected non-terminal {name}, found {n.contents!r}")
    return n


def convert(cst_root: CSTNode) -> Node:
    """SPL_PROG concrete tree -> abstract tree for the type analyzer."""
    return _prog(_nt(cst_root, "SPL_PROG"))


def _prog(n: CSTNode) -> Node:
    # SPL_PROG -> P $
    return Node(Kind.SPL_PROG, [_p(n.children[0])], line=_first_line(n))


def _p(n: CSTNode) -> Node:
    # P -> V_DECL : F_DECL : ALGO
    c = n.children
    return Node(Kind.P, [_v_decl(c[0]), _f_decl(c[2]), _algo(c[4])], line=_first_line(n))


def _v_decl(n: CSTNode) -> Node:
    c = n.children
    if not c:
        return Node(Kind.V_DECL_EPS, line=_first_line(n))
    return Node(Kind.V_DECL_CONS, [_terminal(c[0], Kind.NAME), _v_decl(c[1])], line=c[0].line)


def _f_decl(n: CSTNode) -> Node:
    c = n.children
    if not c:
        return Node(Kind.F_DECL_EPS, line=_first_line(n))
    return Node(Kind.F_DECL_CONS, [_f_type(c[0]), _f_decl(c[1])], line=_first_line(n))


def _f_type(n: CSTNode) -> Node:
    c = n.children
    name, params, body = _terminal(c[1], Kind.NAME), _v_decl(c[3]), _p(c[6])
    if c[0].contents == "void":
        # void NAME ( V_DECL ) { P return }
        return Node(Kind.F_TYPE_VOID, [name, params, body], line=c[0].line)
    # num NAME ( V_DECL ) { P return ( TERM ) }
    return Node(Kind.F_TYPE_NUM, [name, params, body, _term(c[9])], line=c[0].line)


def _algo(n: CSTNode) -> Node:
    c = n.children
    if not c:
        return Node(Kind.ALGO_EPS, line=_first_line(n))
    # ALGO -> INSTR ; ALGO
    return Node(Kind.ALGO_CONS, [_instr(c[0]), _algo(c[2])], line=_first_line(n))


def _outp(n: CSTNode) -> Node:
    c = n.children
    if len(c) == 1:  # OUTP -> STRING
        return Node(Kind.OUTP_STRING, value=c[0].contents, line=c[0].line)
    return Node(Kind.OUTP_TERM, [_term(c[1])], line=_first_line(n))  # ( TERM )


def _instr(n: CSTNode) -> Node:
    c = n.children
    line = _first_line(n)
    head = c[0]
    if head.is_leaf():
        if head.contents == "print":
            return Node(Kind.INSTR_PRINT, [_outp(c[1])], line=line)
        if head.contents == "nop":
            return Node(Kind.INSTR_NOP, line=line)
        if head.contents == "comment":
            return Node(Kind.INSTR_COMMENT, [_terminal(c[1], Kind.STRING)], line=line)
        raise ConversionError(f"unexpected INSTR head {head.contents!r}")
    if head.contents == "ASSIGN":
        return Node(Kind.INSTR_ASSIGN, [_assign(head)], line=line)
    if head.contents == "BRANCH":
        return Node(Kind.INSTR_BRANCH, [_branch(head)], line=line)
    if head.contents == "LOOP":
        return Node(Kind.INSTR_LOOP, [_loop(head)], line=line)
    if head.contents == "CALL":
        return Node(Kind.INSTR_CALL, [_call(head)], line=line)
    raise ConversionError(f"unexpected INSTR child {head.contents!r}")


def _call(n: CSTNode) -> Node:
    # CALL -> NAME ( INPUT )
    c = n.children
    return Node(Kind.CALL, [_terminal(c[0], Kind.NAME), _input(c[2])], line=c[0].line)


def _input(n: CSTNode) -> Node:
    c = n.children
    if not c:
        return Node(Kind.INPUT_EPS, line=_first_line(n))
    return Node(Kind.INPUT_CONS, [_term(c[0]), _input(c[1])], line=_first_line(n))


def _assign(n: CSTNode) -> Node:
    # ASSIGN -> NAME = TERM
    c = n.children
    return Node(Kind.ASSIGN, [_terminal(c[0], Kind.NAME), _term(c[2])], line=c[0].line)


def _term(n: CSTNode) -> Node:
    c = n.children
    line = _first_line(n)
    head = c[0]
    if head.is_leaf():
        if head.contents in _TERM_OPS:
            # op ( TERM TERM )  or  neg ( TERM )
            args = [_term(x) for x in c if not x.is_leaf()]
            return Node(_TERM_OPS[head.contents], args, line=line)
        if head.contents[:1] in ('-', *"0123456789"):  # NUM; NAMEs always start with '#'
            return Node(Kind.TERM_NUM, [_terminal(head, Kind.NUM)], line=line)
        return Node(Kind.TERM_NAME, [_terminal(head, Kind.NAME)], line=line)
    if head.contents == "CALL":
        return Node(Kind.TERM_CALL, [_call(head)], line=line)
    raise ConversionError(f"unexpected TERM child {head.contents!r}")


def _bool(n: CSTNode) -> Node:
    c = n.children
    op = c[0].contents
    if op not in _BOOL_OPS:
        raise ConversionError(f"unexpected BOOL head {op!r}")
    kind = _BOOL_OPS[op]
    if kind in (Kind.BOOL_EQ, Kind.BOOL_LARGER, Kind.BOOL_LESSER):
        args = [_term(x) for x in c if not x.is_leaf()]
    else:
        args = [_bool(x) for x in c if not x.is_leaf()]
    return Node(kind, args, line=c[0].line)


def _branch(n: CSTNode) -> Node:
    # if BOOL then { ALGO } else { ALGO }
    c = n.children
    return Node(Kind.BRANCH, [_bool(c[1]), _algo(c[4]), _algo(c[8])], line=c[0].line)


def _cond(n: CSTNode) -> Node:
    kind = Kind.COND_WHILE if n.children[0].contents == "while" else Kind.COND_UNTIL
    return Node(kind, line=n.children[0].line)


def _loop(n: CSTNode) -> Node:
    c = n.children
    if c[0].is_leaf():
        # do { ALGO } COND BOOL
        return Node(Kind.LOOP_POST, [_algo(c[2]), _cond(c[4]), _bool(c[5])], line=c[0].line)
    # COND BOOL do { ALGO }
    return Node(Kind.LOOP_PRE, [_cond(c[0]), _bool(c[1]), _algo(c[4])], line=_first_line(n))
