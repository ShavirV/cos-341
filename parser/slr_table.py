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

# step 3, construct the LR(0) automaton

def closure(items):
    """
    Closure of the passed in item set
    items are defined as a set of (prod_index, dot_pos)
    
    cheapest way to iterate over everything since we already have the grammar in plain text
    """
    # closure(i) contains i 
    items = set(items)
    changed = True
    while changed:
        changed = False
        new_items = set()
        # split at dot and analyse 
        for (i, dot) in items:
            lhs, rhs = PRODS[i]
            if dot < len(rhs)
                sym = rhs[dot]
                # need to look at NT rule associated with this sym
                if sym in NONTERMINALS:
                    for j, (jlhs, jrhs) in enumerate(PRODS):
                        if jlhs == sym and (j, 0) not in items:
                            new_items.add((j, 0))
        if new_items - items: #theres a set difference so we changed something
            items |= new_items
            changed = True
        return frozenset(items) #frozenset so we're sure its immutable 

def goto(items, sym):
    """
    The GOTO functions for (item, symbol)
    Used to define transitions in the DFA
    """
    moved = set()
    for (i, dot) in items:
        lhs, rhs = PRODS[i]
        if dot < len(rhs) and lhs[dot] == sym:
            moved.add((i, dot + 1)) #accept as transition and move on 
    if not moved:
        return frozenset() # nope
    return closure(moved)

def build_automaton():
    """
    Canonical automaton, idk what else to say we know what this does
    """
    # starting state is represented by closure of item S.$
    start_items = closure({(0,0)})
    states = [start_items] # will be added to
    state_index = {start_items: 0}
    transitions = {} # (state_index, sym) -> state_index
    
    frontier = [start_items] # where we still need to explore
    all_symbols = NONTERMINALS | TERMINALS
    while frontier:
        next_frontier = []
        for items in frontier:
            s_idx = state_index[items]
            # foreach symbol, check if theres a goto for that symbol
            # i.e theres a transition on that symbol for the state we're evaluating
            for sym in all_symbols:
                target = goto(items, sym)
                if not target:
                    continue 
                # we've found a new state to explore later 
                if target not in state_index:
                    state_index[target] = len(states)
                    states.append(target)
                    next_frontier.append(target)
                # keep track of the new transition that we've found
                transitions[(s_idx, sym)] = state_index[target]
        frontier = next_frontier
    return states, transitions

# step 4, build the SLR parse table

class SLRTable:
    """
    Simple class to put all the functions defined above together, 
    goes through the first three steps automatically during construction, and uses that output
    in _build() to construct the actual table with no user involvement
    """
    def __init__(self):
        self.first = compute_first()
        self.follow = compute_follow(self.first)
        self.states, self.automaton = build_automaton()
        self.action = {} # (state, terminal) -> ("shift", state) | ("reduce", prod_idx) | ("accept",)
        self.goto_table = {}
        self._build()
        
        def _conflict(self, state, sym, existing, new):
            ...
        
        def _describe_state(self, state_idx):
            ...
        
        def _build(self):
            """
            The 'main' part of the table construction
            """
            ...
        def build_slr_table() -> SLRTable:
            """
            The only function exposed from this file. in main (or the actual parser), one just
            needs to call this, and the table is automatically returned
            """
            return SLRTable()
                    
                