# Type Analyzer (Phase 2b): Changes and New Features

This document covers the update to `semantics/type_analyzer.py` and the new
tests in `tests/test_type_analyzer.py`. No other files were changed.

## Summary

| Change | Why |
|---|---|
| The mod/div error uses the spec's exact wording | The spec prescribes the message; ours said "might occur" |
| New `number_type` attribute (`"int"` / `"float"`) | Phase 3a needs it to declare its temporary variables |
| One mistake gives one error | A single undeclared name used to produce up to 5 errors |
| Function names are typed from their headers first | Calls to a function with a broken body were reported again as "undeclared" |
| Crude-rule errors point at the right line | They used to report line 1 (the program root) |
| 10 new tests | Cover all of the above; 24/24 pass |

## How the analyzer now works

`analyze()` runs three passes:

1. **Crude rule scan.** One pass over the whole tree looks for `mod`, `div` and
   decimal numbers. It rejects the program if `mod` and `div` both appear, or
   if `mod` appears together with a decimal number. The same scan decides
   `number_type`. If the program is rejected here, nothing else runs.
2. **Function header registration.** Every function name gets its type from
   its keyword (`void` → `procedure`, `num` → `numeric`) before any body is
   checked.
3. **Bottom-up walk.** The rule-by-rule check from the spec, unchanged apart
   from the error handling described below.

## New features

### 1. `number_type` for code generation

After `analyze()`, the analyzer records whether the program works with whole
numbers or real numbers:

| Program contains | `number_type` |
|---|---|
| `mod` | `"int"` |
| `div`, or any number with a decimal point | `"float"` |
| neither | `"int"` |

```python
analyzer = TypeAnalyzer(symtab)
if analyzer.analyze(ast, strict=False):
    temp_type = analyzer.number_type      # "int" or "float"
```

It is reset at the start of every `analyze()` call, so reusing one analyzer
for several programs is safe. The constants `INT` and `FLOAT` are exported
from `type_analyzer.py`.

**Not done yet:** the CLI and `spl_pipeline.py` don't pass `number_type` on
anywhere. That gets wired up when the code generator (3a) is added.

### 2. Exact spec wording for the mod/div error

The message now starts with the sentence from the 2b sheet, followed by where
the two operators are:

```
TYPE ERROR (line 5): A float-integer-conflict might perhaps be possible ('mod' at line 4, 'div' at line 5)
```

The wording is stored in the constant `FLOAT_INT_CONFLICT_MSG`. If the tutor
wants the bare sentence only, remove the bracketed part in
`check_mod_div_conflict()`.

The decimal-dot error also names the line of the first `mod`, and both errors
now carry the line of the offending node instead of line 1.

## Changed behaviour: error cascades

### The rule

When a node fails because one of its children already failed, it now takes on
the error silently instead of reporting again. The original code did this only
for pass-through nodes (`ALGO_CONS`, `INSTR_*`, `P`, …). It now applies to
every rule, including arithmetic, comparisons, assignments, branches, loops
and calls.

**One exception:** function declarations (`F_TYPE_VOID`, `F_TYPE_NUM`) still
report a line naming the function, because "which function does this break"
is useful context. This keeps the behaviour that
`test_cascade_still_names_the_broken_function` expects.

### Before and after

All examples are real output from the old and new analyzer.

**An undeclared name deep in an expression:** `#x = add ( mul ( #z 2 ) 1 ) ;`

Before (4 errors):
```
TYPE ERROR (line 4): Use of '#z' as a numeric TERM requires it to be 'numeric', but it is 'unknown' (...)
TYPE ERROR (line 4): 'mul(...)' requires two numeric operands: 1st operand is 'error'.
TYPE ERROR (line 4): 'add(...)' requires two numeric operands: 1st operand is 'error'.
TYPE ERROR (line 4): Assignment is not well-typed: right-hand side is 'error', expected 'numeric'.
```

After (1 error):
```
TYPE ERROR (line 4): Use of '#z' as a numeric TERM requires it to be 'numeric', but it is 'unknown' (...)
```

**A function with a bad return value, then called:** `num #f` returns an
undeclared `#q`, and the main program does `#x = #f ( ) ;`

Before (5 errors): the root cause, the function, then three more at the call
site (call "undeclared/untyped", call used as a term, assignment).

After (2 errors): the root cause and the function.
```
TYPE ERROR (line 6): Use of '#q' as a numeric TERM requires it to be 'numeric', but it is 'unknown' (...)
TYPE ERROR (line 3): num-function '#f' is not well-typed: return TERM (got 'error', expected 'numeric').
```

The call site stays quiet because pass 2 has already typed `#f` as `numeric`
from its header.

**Independent mistakes are still all reported.** Three undeclared names on
three lines still give three errors.

## Note for the write-up: deviations from the literal spec

- **Header registration.** The spec types a function's name only after its
  body checks out. We type it from the header first. The program is still
  rejected either way; the only difference is fewer follow-up errors.
- **Error message.** The crude-rule message contains the spec's sentence word
  for word, with locations appended.

## Tests

Ten tests were added to `tests/test_type_analyzer.py` (sections 11–13).
The original 14 are unchanged.

| Section | Tests | What they check |
|---|---|---|
| 11 | `test_mod_div_conflict_uses_spec_wording` | The error starts with the spec sentence |
| 12 | `test_number_type_is_int_when_mod_is_used`, `..._float_when_div_is_used`, `..._float_for_a_decimal_literal_without_div`, `..._int_for_plain_whole_numbers`, `..._reset_between_runs` | All `number_type` cases, plus reuse of one analyzer |
| 13 | `test_call_to_broken_function_is_not_reported_again`, `test_fault_deep_in_an_expression_yields_single_error`, `test_fault_inside_a_branch_yields_single_error`, `test_independent_faults_are_all_reported` | Cascade control, without hiding separate mistakes |

Run them with:

```bash
python3 -m tests.test_type_analyzer      # expect: 24 passed, 0 failed out of 24
```

All 10 new tests fail against the old `type_analyzer.py`, so each one checks a
real change. The full suite (`python3 test.py`, needs pytest) also covers
`tests/test_pipeline.py` and the CLI.

## Known limitations

- **Argument counts aren't checked.** Calling a function with the wrong number
  of arguments passes both 2a and 2b, because neither spec sheet asks for this
  check. Inlining in 3b will need the counts to match, so ask the tutor
  whether it belongs in 2a.
- **The bottom-up walk is still recursive.** Very long programs can hit
  Python's recursion limit. `spl_pipeline.py` already catches this and reports
  it, and the new crude-rule scan is iterative.
