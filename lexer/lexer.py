from dataclasses import dataclass

# Spec says blank_space is ASCII 32 (space) or ASCII 13 (\r).
# We additionally treat \n as blank_space: Unix line endings have no \r at
# all, and Windows \r\n would otherwise be split as \r (blank) followed by
# a bare \n glued onto the next token. This goes beyond the literal spec --
# flag it in your write-up.
BLANKS = {' ', '\r', '\n'}

DIGIT_A = '0'
DIGITS_B = set('123456789')
ALPHANUM = set('0123456789abcdefghijklmnopqrstuvwxyz')
STRING_CHARS = set(',.:-?!') | set('0123456789abcdefghijklmnopqrstuvwxyz')

KEYWORDS = {
    "void", "num", "print", "if", "then", "else", "while", "until", "do",
    "nop", "comment", "mod", "add", "sub", "mul", "div", "neg",
    "and", "or", "not", "eq", "larger", "lesser", "return",
}
SYMBOLS = set("(){}:;=$")


@dataclass
class Token:
    kind: str
    lexeme: str
    line: int
    col: int

    def __repr__(self):
        return f"Token({self.kind!r}, {self.lexeme!r}, {self.line}:{self.col})"


class LexError(Exception):
    def __init__(self, message, line, col):
        super().__init__(f"Lexical error at line {line}, col {col}: {message}")
        self.line = line
        self.col = col


# ---------------------------------------------------------------------------
# NUM DFA -- states: A, D, Z, C, B, GH, I (as derived on paper)
# Returns (end, final, state) where `end` is how far the DFA got before
# getting stuck (or running out of input), `final` says whether that
# stopping state is accepting, and `state` is the stuck-at state, used for
# diagnostics when the chunk is rejected.
# ---------------------------------------------------------------------------
def run_num(chunk):
    state = 'A'
    i = 0
    n = len(chunk)
    while i < n:
        c = chunk[i]
        nxt = None
        if state == 'A':
            if c == '-':
                nxt = 'D'
            elif c == DIGIT_A:
                nxt = 'C'
            elif c in DIGITS_B:
                nxt = 'B'
        elif state == 'D':
            if c == DIGIT_A:
                nxt = 'Z'
            elif c in DIGITS_B:
                nxt = 'B'
        elif state == 'Z':
            if c == '.':
                nxt = 'GH'
        elif state == 'C':
            if c == '.':
                nxt = 'GH'
        elif state == 'B':
            if c == DIGIT_A or c in DIGITS_B:
                nxt = 'B'
            elif c == '.':
                nxt = 'GH'
        elif state == 'GH':
            if c == DIGIT_A:
                nxt = 'GH'
            elif c in DIGITS_B:
                nxt = 'I'
        elif state == 'I':
            if c == DIGIT_A:
                nxt = 'GH'
            elif c in DIGITS_B:
                nxt = 'I'
        if nxt is None:
            return i, state in ('B', 'C', 'I'), state
        state = nxt
        i += 1
    return i, state in ('B', 'C', 'I'), state


NUM_STATE_HINTS = {
    'A': "expected a digit or '-' to start a number",
    'D': "expected a digit after '-'",
    'Z': "'-0' must be followed by '.' (a lone signed zero is not allowed)",
    'C': "a leading '0' cannot be followed by more digits "
         "(only '0' alone, or '0.xxx', is allowed)",
    'B': "expected a digit or '.' to continue the integer part",
    'GH': "expected another digit after the decimal point "
          "(the fraction must end in a non-zero digit)",
    'I': "expected another digit to continue the fraction",
}


def match_num(chunk):
    end, final, state = run_num(chunk)
    if final and end == len(chunk):
        return True, None
    if end == len(chunk):
        # consumed the whole chunk but landed in a non-final state --
        # use the same state-specific hint table as the "got stuck" case
        return False, f"malformed number {chunk!r}: {NUM_STATE_HINTS.get(state, 'incomplete number')}"
    # got stuck partway through -- report the offending character and why
    stuck_char = chunk[end]
    return False, f"malformed number: at {stuck_char!r} (position {end} " \
                   f"in {chunk!r}), {NUM_STATE_HINTS.get(state, 'unexpected character')}"


# ---------------------------------------------------------------------------
# USER-DEFINED-NAME DFA -- states: S0, S1
# ---------------------------------------------------------------------------
def match_name(chunk):
    if not chunk or chunk[0] != '#':
        return False, None
    for i, c in enumerate(chunk[1:], start=1):
        if c not in ALPHANUM:
            return False, (f"malformed name: {c!r} at position {i} in "
                            f"{chunk!r} is not allowed (only 0-9, a-z after '#')")
    return True, None  # '#' alone, or '#' + alphanumerics, is always final


# ---------------------------------------------------------------------------
# STRING DFA -- states: S0, S1, S2
# ---------------------------------------------------------------------------
def match_string(chunk):
    if not chunk or chunk[0] != '"':
        return False, None
    if len(chunk) < 2 or chunk[-1] != '"':
        return False, f"unterminated string: {chunk!r} has no closing '\"'"
    body = chunk[1:-1]
    for i, c in enumerate(body, start=1):
        if c not in STRING_CHARS:
            return False, (f"malformed string: {c!r} at position {i} in "
                            f"{chunk!r} is not in the allowed STRING alphabet "
                            f"(no spaces allowed inside a STRING literal)")
    return True, None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def classify(chunk):
    """Returns (kind, reason). kind is None on failure, with reason set to
    the most relevant diagnostic message collected along the way."""
    if chunk in KEYWORDS:
        return 'KEYWORD', None
    if len(chunk) == 1 and chunk in SYMBOLS:
        return 'SYMBOL', None

    reasons = []
    if chunk.startswith('#'):
        ok, reason = match_name(chunk)
        if ok:
            return 'NAME', None
        if reason:
            reasons.append(reason)
    elif chunk.startswith('"'):
        ok, reason = match_string(chunk)
        if ok:
            return 'STRING', None
        if reason:
            reasons.append(reason)
    elif chunk[:1] == '-' or chunk[:1].isdigit():
        ok, reason = match_num(chunk)
        if ok:
            return 'NUM', None
        if reason:
            reasons.append(reason)

    if reasons:
        return None, reasons[0]
    return None, (f"{chunk!r} is not a keyword, symbol, or a valid "
                   f"NUM / USER-DEFINED-NAME / STRING token")


# ---------------------------------------------------------------------------
# Driver: split on blanks, classify each chunk, track line/col incrementally
# ---------------------------------------------------------------------------
REQUIRE_TRAILING_BLANK_AFTER_LAST_TOKEN = True


def tokenize(text):
    tokens = []
    i, n = 0, len(text)
    line, col = 1, 1
    last_token_end_was_blank = True  # true before any token, vacuously

    while i < n:
        c = text[i]

        if c in BLANKS:
            if c == '\r' and i + 1 < n and text[i + 1] == '\n':
                i += 2  # treat \r\n as one newline
            else:
                i += 1
            line += 1 if c in ('\r', '\n') else 0
            col = 1 if c in ('\r', '\n') else col + 1
            last_token_end_was_blank = True
            continue

        start_line, start_col = line, col
        j = i
        while j < n and text[j] not in BLANKS:
            j += 1
        chunk = text[i:j]

        kind, reason = classify(chunk)
        if kind is None:
            raise LexError(reason, start_line, start_col)

        tokens.append(Token(kind, chunk, start_line, start_col))
        col += (j - i)
        i = j
        last_token_end_was_blank = (i < n and text[i] in BLANKS)

    if tokens and REQUIRE_TRAILING_BLANK_AFTER_LAST_TOKEN and not last_token_end_was_blank:
        last = tokens[-1]
        raise LexError(
            f"final token {last.lexeme!r} is not followed by blank_space "
            f"before end of file (spec requires every token to end with one)",
            last.line, last.col,
        )

    return tokens


if __name__ == "__main__":
    good = '#x 0 -0.5 5 -5 0.5 "hello,world" if while $ '
    print("--- valid program fragment ---")
    for tok in tokenize(good):
        print(tok)

    print("\n--- error diagnostics ---")
    bad_cases = [
        '5. ',            # malformed number: nothing after '.'
        '"abc ',          # unterminated string (space breaks it, then EOF)
        '-0 ',             # lone signed zero
        '00 ',             # leading zero followed by digit
        '--5 ',            # double minus
        '#h@llo ',         # bad char in name
        'foo ',            # not a keyword/symbol/anything
        '#x 0',            # missing trailing blank on last token
    ]
    for s in bad_cases:
        try:
            toks = tokenize(s)
            print(f'{s!r}: UNEXPECTEDLY ACCEPTED -> {toks}')
        except LexError as e:
            print(f'{s!r}: {e}')
