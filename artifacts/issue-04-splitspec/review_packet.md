# SplitSpec Review Packet — Issue issue-04

## Decision
ACCEPT

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: PASS (valid: True; ran: True)
- Patch edited an existing test: False

## Issue
Money rounding

Yen-denominated prices show two decimal places, but the yen has no subunits,
so a 1200-yen ticket comes back as 1200.00 and fractional-yen inputs produce
amounts that cannot exist as currency. Our client-side totals have to match
the server exactly, so prices in non-decimal currencies should round to whole
numbers. Everything priced in dollars looks fine.

- Out of scope: Rounding or formatting behavior for currencies that have decimal sub‑units (e.g., USD, EUR)., Presentation layer formatting such as UI display of currency symbols., Database storage details of monetary values.

## Behavioral invariant
- When the currency associated with a monetary amount has zero decimal sub‑units (e.g., JPY), the server’s serialized representation of that amount must contain no fractional part.
- For such currencies the numeric value returned by the server must be an integer that corresponds to the input amount rounded to a whole number.

## Candidate patch
- Files changed: app/money.py, test_issue_04_resolved.py, test_jpy_api_integration.py, test_jpy_comprehensive.py, test_jpy_issue.py
- Patch size: +192/-1 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Successfully resolved issue-04 by updating app/money.py to correctly handle JPY currency with 0 decimal places. Changes made: 1. Updated SUPPORTED dictionary: Changed "JPY": 2 to "JPY": 0 2. Enhanced render() function: Added special handling for currencies with 0 decimal places to return integer strings The fix ensures: - JPY amounts are serialized as integers without decimal places (e.g., "1200" instead of "1200.00") - Fractional JPY amounts are rounded to whole numbers using round-half-up (e.g., 1200.5 → 1201) - Client-side calculations will match server totals exactly - All existing USD and... [truncated, 764 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 4 tests, 0 failed, 0 errors
```
....                                                                     [100%]
4 passed in 0.05s
```

## Independent verifier test
PASS - 2 tests, 0 failed, 0 errors
- Invariant: When the currency is JPY, the serialized monetary amount must be an integer without fractional components, rounded to the nearest whole number.
- Assumptions:
  - The system uses 'money.render' to serialize monetary amounts to strings.
  - JPY should have zero decimal places instead of the current two.
  - The expected rounding for JPY is round-half-up (1200.5 -> 1201).
- Validity: valid (compiles=True, runs=True, fails_on_original_bug=True) — test failed on the buggy code (2 failures) as expected

## Gold hidden evaluator
PASS - 5 tests, 0 failed, 0 errors

## Mutation sensitivity
Detected 3/4 incorrect variants. A below-ceiling score may reflect a mutant no in-process test can kill (a manifest ceiling), not a test failure.
- Killed: 3/4

## Residual risks
- Contract ambiguity: The exact rounding rule for fractional yen inputs (nearest, round‑half‑up, floor, ceiling) is not specified.
- Contract ambiguity: Whether the price field is returned as a numeric type or as a string containing the integer value is not clarified.
- Contract ambiguity: Whether the rounding should be applied at input validation time, storage time, or serialization time is not defined.
- Out of scope (unaddressed): Rounding or formatting behavior for currencies that have decimal sub‑units (e.g., USD, EUR).
- Out of scope (unaddressed): Presentation layer formatting such as UI display of currency symbols.
- Out of scope (unaddressed): Database storage details of monetary values.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.