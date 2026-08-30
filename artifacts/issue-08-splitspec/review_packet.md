# SplitSpec Review Packet — Issue issue-08

## Decision
ACCEPT

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: PASS (valid: True; ran: True)
- Patch edited an existing test: False

## Issue
Retry causes duplicate side effect

When a payment request times out and the client retries with the same
Idempotency-Key, sometimes two payments are created instead of one.
The retry should be idempotent - same key means same payment. But we're
seeing duplicate charges on the bank side. The Idempotency-Key header
is supposed to prevent this but it seems like the check happens too late.

- Out of scope: How the client detects a timeout or decides to retry., The internal storage mechanism for Idempotency-Key values., Performance characteristics or latency of the idempotency check., Any behavior unrelated to the payment creation endpoint (e.g., other routes).

## Behavioral invariant
- For any given Idempotency-Key value, the payment service must create at most one payment record and trigger at most one external charge, regardless of how many times the client repeats the request.
- When a request with a previously seen Idempotency-Key is received, the service must return the same response (e.g., payment ID, status) as the original request without performing the side‑effect again.

## Candidate patch
- Files changed: app/routes/payments.py, test_idempotency_race.py, test_race_condition.py
- Patch size: +127/-5 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed idempotency issue in payment service by adding upfront check for existing payments before creation. The fix ensures that retry requests with the same Idempotency-Key return the existing payment instead of creating duplicates. Modified app/routes/payments.py to check for existing payments first, handle race conditions properly, and maintain all existing functionality. All visible tests pass.

## Visible tests
PASS - 6 tests, 0 failed, 0 errors
```
......                                                                   [100%]
6 passed in 0.11s
```

## Independent verifier test
PASS - 1 tests, 0 failed, 0 errors
- Invariant: For any given Idempotency-Key value, the payment service must create at most one payment record, and retries must return the original payment record identifier.
- Assumptions:
  - The application's payment endpoint (/payments) uses the 'Idempotency-Key' header.
  - The application assigns a unique integer ID to each payment record.
- Validity: valid (compiles=True, runs=True, fails_on_original_bug=True) — test failed on the buggy code (1 failures) as expected

## Gold hidden evaluator
PASS - 3 tests, 0 failed, 0 errors

## Mutation sensitivity
Detected 2/5 incorrect variants. A below-ceiling score may reflect a mutant no in-process test can kill (a manifest ceiling), not a test failure.
- Killed: 2/5

## Residual risks
- Contract ambiguity: Exact URL path of the payment endpoint (e.g., /payments, /api/payments).
- Contract ambiguity: Schema of the request payload required to create a payment.
- Contract ambiguity: Definition of "timeout" from the client perspective (network timeout, server 5xx, etc.).
- Contract ambiguity: Whether the service should return the original response body verbatim or may return a generic idempotent acknowledgment.
- Contract ambiguity: How the external bank charge is observed or logged for verification.
- Out of scope (unaddressed): How the client detects a timeout or decides to retry.
- Out of scope (unaddressed): The internal storage mechanism for Idempotency-Key values.
- Out of scope (unaddressed): Performance characteristics or latency of the idempotency check.
- Out of scope (unaddressed): Any behavior unrelated to the payment creation endpoint (e.g., other routes).

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.