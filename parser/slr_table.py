"""
A generic algorithm for constructing an SLR(1) table

In case we only need it to work with the grammar defined in grammar.py
But any SLR parseable grammar formatted using the same rules would work

Builds:

1) FIRST sets
2) FOLLOW sets
3) The canonical automaton of LR(0) item sets
4) Finally the SLR ACTION & GOTO tables

will raise an error if the grammar is not in the class SLR(1),
meaning it won't allow conflicts on any table indices. Shouldn't be a
problem for this grammar
"""

from collections import defaultdict
from grammar import PRODUCTIONS, NONTERMINALS, TERMINALS, START, EPS

AUGMENTED_START = START + "'"

class GrammarConflictError(Exception):
    pass

def _productions_with_augment():
    # We always start with the augmented production S' -> S
    return [(AUGMENTED_START, (START,))] + PRODUCTIONS

PRODS = _productions_with_augment()


# step 1, get the FIRST sets

def compute_first():
    # terminal's first sets are just itself
    first = {t: {t} for t in TERMINALS}
    
    # more complex for nonterminals
    for nt in NONTERMINALS:
        first[nt] = set()
    first[AUGMENTED_START] = set()
    
    changed = True
    while changed:
        changed = False
        for lhs, rhs in PRODS:
            # should EPSILON be in this first set?
            if rhs is EPS or len(rhs) == 0:
                if EPS not in first[lhs]:
                    first[lhs].add(EPS)
                    changed = True
                continue
            # if NULLABLE prefix a, First(ab) = First(a) u First(b)
            nullable_prefix = True
            for sym in rhs:
                sym_first = first[sym] - {EPS}
                before = len(first[lhs])
                first[lhs] |= sym_first # inplace bitwise or to check if already there
                if (len(first[lhs]) != before): #bitwise or actually did something 
                    changed = True
                if EPS not in first[sym]:
                    nullable_prefix = False
                    break
            # if NULLABLE prefix a, EPS in FIRST(a)
            if nullable_prefix: 
                if EPS not in first[lhs]:
                    first[lhs].add(EPS)
                    changed = True
    return first
                    
                