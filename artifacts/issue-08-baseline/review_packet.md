# SplitSpec Review Packet — Issue issue-08

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: medium
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Retry causes duplicate side effect

When a payment request times out and the client retries with the same
Idempotency-Key, sometimes two payments are created instead of one.
The retry should be idempotent - same key means same payment. But we're
seeing duplicate charges on the bank side. The Idempotency-Key header
is supposed to prevent this but it seems like the check happens too late.

- Out of scope: Requests that use a different Idempotency-Key., Endpoints unrelated to payment creation., Behavior of network timeouts or client‑side retry logic beyond the Idempotency-Key semantics., Bank‑side failures unrelated to duplicate request handling.

## Behavioral invariant
- For any given Idempotency-Key, the system must create at most one payment record.
- A subsequent request with the same Idempotency-Key must return the same observable response as the original request and must not trigger a new payment creation.

## Candidate patch
- Files changed: app/routes/payments.py, cleanup.py, test_idempotency_fix.py, test_race_condition.py
- Patch size: +84/-5 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; ## Summary I successfully fixed the idempotency issue in the payment processing system. The problem was that the original code didn't check for existing payments with the same idempotency key before creating a new payment, which could lead to duplicate payments when requests were retried. ### Changes Made **File: `app/routes/payments.py`** 1. **Added early idempotency check**: Before creating a new payment, the code now checks if a payment with the same idempotency key already exists. 2. **Fixed the logic flow**: The original code had a problematic section after the commit that would just pass... [truncated, 1872 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 6 tests, 0 failed, 0 errors
```
......                                                                   [100%]
6 passed in 0.11s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
PASS - 3 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: Exact URL path, HTTP method, and required payload fields for the payment request.
- Contract ambiguity: Definition of the "timeout" condition (e.g., client‑side socket timeout, server‑side processing deadline).
- Contract ambiguity: The expected HTTP status code and response body for an idempotent retry.
- Contract ambiguity: Whether payment processing is synchronous or asynchronous, and how that affects when the Idempotency-Key check occurs.
- Contract ambiguity: Database schema details that record Idempotency-Key values.
- Contract ambiguity: Concurrency model (e.g., whether two requests can be processed in parallel) and any locking mechanisms.
- Out of scope (unaddressed): Requests that use a different Idempotency-Key.
- Out of scope (unaddressed): Endpoints unrelated to payment creation.
- Out of scope (unaddressed): Behavior of network timeouts or client‑side retry logic beyond the Idempotency-Key semantics.
- Out of scope (unaddressed): Bank‑side failures unrelated to duplicate request handling.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.