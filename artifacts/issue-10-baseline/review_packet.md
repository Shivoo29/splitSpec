# SplitSpec Review Packet — Issue issue-10

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Some invoice totals are one cent lower than the customer was quoted

A customer complained that their invoice said 1.02 when the quote said 1.03.
We checked a few more and found the same thing on several orders, always
exactly one cent, always on amounts ending in half a cent. Most orders are
fine. Our finance team says amounts ending in half a cent must always round
up, never down. There is a test in the suite that covers this and it is
currently failing.

- Out of scope: Rounding of tax, discounts, or other derived amounts unless they contain a half‑cent fraction., Currency conversion, multi‑currency handling, or locale‑specific formatting., Database persistence, API authentication, or UI layout concerns.

## Behavioral invariant
- When a monetary value has a fractional component of exactly 0.005 (i.e., a half‑cent), the system must round that value up to the next cent rather than down.
- The invoice total presented to the customer must equal the quoted amount after applying the rounding‑up rule to any half‑cent components.

## Candidate patch
- Files changed: app/money.py, test_additional_cases.py
- Patch size: +37/-3 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed issue-10 by changing the rounding mode in app/money.py from ROUND_HALF_EVEN (banker's rounding) to ROUND_HALF_UP (commercial rounding). This ensures that half-cent values (e.g., 1.025, 2.035) round up instead of down, preventing invoice totals from being one cent lower than quoted amounts. Changes made: - Modified app/money.py: Changed import from ROUND_HALF_EVEN to ROUND_HALF_UP - Modified app/money.py: Updated quantize() function to use ROUND_HALF_UP - Modified app/money.py: Updated module docstring to reflect commercial rounding All tests pass: - test_half_cent_rounds_up: PASSED - tes... [truncated, 790 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.01s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
PASS - 5 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: Exact numeric type used for monetary values (Decimal, float, integer cents, etc.).
- Contract ambiguity: Whether rounding is applied per line‑item before aggregation or only on the final total.
- Contract ambiguity: How negative amounts or refunds should be rounded.
- Contract ambiguity: Whether the rule applies to all monetary fields (e.g., tax, fees) or only to the base price.
- Out of scope (unaddressed): Rounding of tax, discounts, or other derived amounts unless they contain a half‑cent fraction.
- Out of scope (unaddressed): Currency conversion, multi‑currency handling, or locale‑specific formatting.
- Out of scope (unaddressed): Database persistence, API authentication, or UI layout concerns.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.