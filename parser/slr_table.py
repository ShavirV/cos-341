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

def first_of_sequence(seq, first):
    """
    check the FIRST set of a sequence of symbols
    this is used for lookahead computation 
    """
    result = set()
    nullable = True
    for sym in seq:
        # exclude epsilon we dont need it here
        sym_first = first[sym] - {EPS}
        
        result |= sym_first
        if EPS not in first[sym]:
            nullable = False
            break
        if nullable:
            result.add(EPS)
        return result

# step 2, compute the follow sets

def compute_follow(first):
    follow = {nt: set() for nt in NONTERMINALS}
    follow[AUGMENTED_START] = {"#"} # HASH used to represent EOF
    follow[START] |= {"#"} # this will also be achieved through transitivity but its kept here for clarity
    
    changed = True
    while changed:
        changed = False
        for lhs, rhs in PRODS:
            for i, sym in enumerate(rhs):
                if sym not in NONTERMINALS:
                    continue
                rest = rhs[i + 1:]
                rest_first = first_of_sequence(rest, first) if rest else {EPS}
                before = len(follow[sym])
                follow[sym] |= (rest_first - {EPS})
                if EPS in rest_first:
                    follow[sym] |= follow[lhs]
                if len(follow[sym]) != before:
                    changed = True
    return follow

                    
                