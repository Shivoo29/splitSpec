# SplitSpec Review Packet — Issue issue-10

## Decision
ACCEPT

Decision inputs:
- Contract confidence: high
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: PASS (valid: True; ran: True)
- Patch edited an existing test: False

## Issue
Some invoice totals are one cent lower than the customer was quoted

A customer complained that their invoice said 1.02 when the quote said 1.03.
We checked a few more and found the same thing on several orders, always
exactly one cent, always on amounts ending in half a cent. Most orders are
fine. Our finance team says amounts ending in half a cent must always round
up, never down. There is a test in the suite that covers this and it is
currently failing.

- Out of scope: Rounding behavior for amounts that do not end in a half‑cent., Currency handling other than the primary currency used by the system., Tax, discount, or fee calculations that may affect the final amount., Formatting or presentation details unrelated to the rounding rule.

## Behavioral invariant
- If the computed monetary amount has a fractional part equal to exactly half a cent (0.005 of a dollar), the system must round the amount up to the next whole cent.

## Candidate patch
- Files changed: app/money.py, test_half_cent_fix.py
- Patch size: +34/-2 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; ## Summary I successfully resolved issue-10 where invoice totals were rounding down for amounts with a half-cent fraction, but finance policy requires them to round up. ### Changes Made - **File modified**: `app/money.py` - **Change**: Changed the rounding method from `ROUND_HALF_EVEN` (bankers rounding) to `ROUND_HALF_UP` in the `quantize()` function - **Specific change**: Line 3 - imported `ROUND_HALF_UP` instead of `ROUND_HALF_EVEN`, and line 27 - changed the rounding parameter from `ROUND_HALF_EVEN` to `ROUND_HALF_UP` ### Why This Fix Works - `ROUND_HALF_EVEN` (bankers rounding) rounds hal... [truncated, 1504 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.01s
```

## Independent verifier test
PASS - 1 tests, 0 failed, 0 errors
- Invariant: If a monetary amount has a fractional part of exactly 0.005 (a half-cent), it must be rounded up to the next cent (e.g., 1.025 -> 1.03). This verifies that the application correctly uses a round-half-up policy instead of the currently implemented round-half-even (bankers) policy, which rounds to the nearest even digit and causes premature rounding down on values like 1.025.
- Assumptions:
  - The currency is USD, which has 2 decimal places.
  - The input to `money.quantize` is a Decimal object or a string/number that converts to it.
  - The environment includes the `app` package.
- Validity: valid (compiles=True, runs=True, fails_on_original_bug=True) — test failed on the buggy code (1 failures) as expected

## Gold hidden evaluator
PASS - 5 tests, 0 failed, 0 errors

## Mutation sensitivity
Detected 4/4 incorrect variants
- Killed: 4/4

## Residual risks
- Out of scope (unaddressed): Rounding behavior for amounts that do not end in a half‑cent.
- Out of scope (unaddressed): Currency handling other than the primary currency used by the system.
- Out of scope (unaddressed): Tax, discount, or fee calculations that may affect the final amount.
- Out of scope (unaddressed): Formatting or presentation details unrelated to the rounding rule.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.