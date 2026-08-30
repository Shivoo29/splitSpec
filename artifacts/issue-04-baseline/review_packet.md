# SplitSpec Review Packet — Issue issue-04

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Money rounding

Yen-denominated prices show two decimal places, but the yen has no subunits,
so a 1200-yen ticket comes back as 1200.00 and fractional-yen inputs produce
amounts that cannot exist as currency. Our client-side totals have to match
the server exactly, so prices in non-decimal currencies should round to whole
numbers. Everything priced in dollars looks fine.

- Out of scope: Rounding behavior for currencies that have sub‑units (e.g., USD, EUR)., Presentation formatting on the client UI beyond the numeric value returned by the API., Currency conversion logic.

## Behavioral invariant
- When the currency of a monetary value has zero sub‑unit digits (e.g., JPY), the server must round the value to an integer number of the major unit before storing or returning it.
- The string representation of such a value returned by any API must contain no decimal point or fractional digits.

## Candidate patch
- Files changed: app/money.py, test_currency_support.py, test_issue_04_fix.py, test_jpy_api.py, test_jpy_edge_cases.py, test_jpy_integration.py, test_jpy_rounding.py, test_seed_jpy.py
- Patch size: +367/-1 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed issue-04 by changing JPY from 2 to 0 decimal places in app/money.py. This ensures JPY amounts are rounded to integers and rendered without decimal points, while maintaining all existing USD and other currency functionality. All tests pass.

## Visible tests
PASS - 4 tests, 0 failed, 0 errors
```
....                                                                     [100%]
4 passed in 0.05s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
PASS - 5 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: Exact rounding rule to apply for fractional inputs (e.g., round half‑up, floor, ceiling).
- Contract ambiguity: Which API endpoints or model fields are responsible for applying the rounding (creation, update, retrieval).
- Contract ambiguity: Whether the integer value should be returned as a number type or as a string without a decimal point.
- Out of scope (unaddressed): Rounding behavior for currencies that have sub‑units (e.g., USD, EUR).
- Out of scope (unaddressed): Presentation formatting on the client UI beyond the numeric value returned by the API.
- Out of scope (unaddressed): Currency conversion logic.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.