# SplitSpec Review Packet — Issue issue-11

## Decision
ESCALATE

Decision inputs:
- Contract confidence: low
- Expect escalation (case rule): True
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Registrations occasionally disappear

Something is wrong with registrations. A user told us on Monday that their
registration was "gone", but when we looked at the account it was there. Our
support lead thinks she saw the same thing last month on a different account
but she is not sure it was the same problem. It might be related to the
mobile app, or to the email confirmations, we are not certain which. We do
not have the account id or a timestamp any more. Nobody has been able to make
it happen on purpose. Please fix.


## Behavioral invariant
None captured — the contract was not produced (or was unreadable).
## Candidate patch
- Files changed: n/a
- Patch size: +0/-0 lines
- Stop reason: length
- Patch notes: stop_reason=length; Good, the type annotation is correct: `event: Mapped[Event]`. I must have misread it earlier. Let me think about this issue one more time. The problem is that registrations "occasionally disappear". This is a rare and intermittent issue that cannot be reliably reproduced. One possibility is that there's a race condition in the database. For example, if two transactions try to update the same registration at the same time, one of them might fail or roll back. But looking at the code, I don't see any obvious race conditions. The code uses SQLAlchemy's default transaction management, which should... [truncated, 35907 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.07s
```

## Independent verifier test
n/a
- Invariant: Registrations, once created or re-activated (following cancellation), must be immediately visible in the user's registration list.
- Assumptions:
  - The API should consistently return all confirmed or cancelled registrations associated with the user.
  - Database transactions are correctly committed and visible after the API call returns.
- Validity: invalid/gated (compiles=None, runs=None, fails_on_original_bug=None) — no buggy variant: case has no seeded bug for the test to catch

## Gold hidden evaluator
PASS - 4 tests, 0 failed, 0 errors

## Mutation sensitivity
Detected 0/3 incorrect variants
- Killed: 0/3

## Residual risks
- Fixer stopped with reason 'length' rather than 'finished' — the patch may be a truncated attempt and evidence below may be partial.
- Contract ambiguity: No specific account identifier or registration ID is provided.
- Contract ambiguity: No timestamp or timeframe of when the disappearance was observed.
- Contract ambiguity: No reproducible steps or conditions that trigger the issue.
- Contract ambiguity: Unclear whether the problem occurs in the web UI, mobile app, email confirmations, or backend API.
- Contract ambiguity: Environment details (development, staging, production) are missing.
- Contract ambiguity: No logs, error messages, or stack traces are supplied.
- Case is marked expect_escalation; it is scored on whether the run escalated, not on patch correctness.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.