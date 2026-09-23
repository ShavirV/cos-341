"""
The grammar for SPL encoded as plain strings such that we can build
the SLR table algorithmically 

- NONTERMINALS are represented as the exact strings as in the spec
- Every other string is a terminal
- EPSILON is represented as (), the empty tuple, in the RHS
- '#' is used as the eof marker (check if this assumption works in practice)

- Not sure if this is the right way of going about it but simple strings are used
for all keywords, since I assume all nuance is abstracted away by the lexer, it'll
just provide us with the lexical class which we work with in the parser

"""

START = "SPL_PROG"
EPS = () # so its actually readable

# tuple of (LHS, RHS)
PRODUCTIONS = [
    ("SPL_PROG", ("P", "$")), # rule 0
    
        ("SPL_PROG", ("P", "$")),

    ("P", ("V_DECL", ":", "F_DECL", ":", "ALGO")),

    ("V_DECL", EPS),
    ("V_DECL", ("USER-DEFINED-NAME", "V_DECL")),

    ("F_DECL", EPS),
    ("F_DECL", ("F_TYPE", "F_DECL")),

    ("F_TYPE", ("void", "USER-DEFINED-NAME", "(", "V_DECL", ")", "{", "P", "return", "}")),
    ("F_TYPE", ("num", "USER-DEFINED-NAME", "(", "V_DECL", ")", "{", "P", "return", "(", "TERM", ")", "}")),

    ("ALGO", EPS),
    ("ALGO", ("INSTR", ";", "ALGO")),

    ("OUTP", ("(", "TERM", ")")),
    ("OUTP", ("STRING",)),

    ("INSTR", ("print", "OUTP")),
    ("INSTR", ("nop",)),
    ("INSTR", ("comment", "STRING")),
    ("INSTR", ("ASSIGN",)),
    ("INSTR", ("BRANCH",)),
    ("INSTR", ("LOOP",)),
    ("INSTR", ("CALL",)),

    ("CALL", ("USER-DEFINED-NAME", "(", "INPUT", ")")),

    ("INPUT", EPS),
    ("INPUT", ("TERM", "INPUT")),

    ("ASSIGN", ("USER-DEFINED-NAME", "=", "TERM")),

    ("TERM", ("USER-DEFINED-NAME",)),
    ("TERM", ("NUM",)),
    ("TERM", ("CALL",)),
    ("TERM", ("mod", "(", "TERM", "TERM", ")")),
    ("TERM", ("add", "(", "TERM", "TERM", ")")),
    ("TERM", ("sub", "(", "TERM", "TERM", ")")),
    ("TERM", ("mul", "(", "TERM", "TERM", ")")),
    ("TERM", ("div", "(", "TERM", "TERM", ")")),
    ("TERM", ("neg", "(", "TERM", ")")),

    ("BRANCH", ("if", "BOOL", "then", "{", "ALGO", "}", "else", "{", "ALGO", "}")),

    ("BOOL", ("not", "(", "BOOL", ")")),
    ("BOOL", ("and", "(", "BOOL", "BOOL", ")")),
    ("BOOL", ("or", "(", "BOOL", "BOOL", ")")),
    ("BOOL", ("eq", "(", "TERM", "TERM", ")")),
    ("BOOL", ("larger", "(", "TERM", "TERM", ")")),
    ("BOOL", ("lesser", "(", "TERM", "TERM", ")")),

    ("LOOP", ("COND", "BOOL", "do", "{", "ALGO", "}")),
    ("LOOP", ("do", "{", "ALGO", "}", "COND", "BOOL")),

    ("COND", ("while",)),
    ("COND", ("until",)),
]

# to make our life easier
NONTERMINALS = {lhs for lhs, _ in PRODUCTIONS}
ALL_RHS_SYMBOLS = {sym for _, rhs in PRODUCTIONS for sym in rhs} # since rhs can compose of many symbols, a tuple of tuples
TERMINALS = (ALL_RHS_SYMBOLS - NONTERMINALS) | {"#"} # python got set operations what a banger

# terminals that are associated with a lexical category. will defined by 'class' not 'text'
KIND_TERMINALS = {"NUM", "USER-DEFINED-NAME", "STRING"}S