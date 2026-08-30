# SplitSpec Review Packet — Issue issue-05

## Decision
REVIEW REQUIRED

Decision inputs:
- Contract confidence: high
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Cross-user ticket access

I can view other people's tickets. When I request a ticket that one of my
teammates was issued, the API returns its full details instead of refusing
me. I was able to read the code of a co-worker's ticket by guessing its id,
which means ticket barcodes are effectively public. Each user should only be
able to read tickets issued to them.

- Out of scope: Ticket creation, update, or deletion behavior., Authorization rules for admin or privileged roles., Non‑ticket related endpoints.

## Behavioral invariant
- When an authenticated request is made to retrieve a ticket, the system must return the ticket details only if the ticket is owned by the requesting user.
- If the ticket is not owned by the requesting user, the system must not return the ticket details and must respond with an access‑denied status.

## Candidate patch
- Files changed: app/routes/tickets.py, final_verification_test.py, test_cross_user_access.py, test_vulnerability.py
- Patch size: +282/-0 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed cross-user ticket access vulnerability by adding ownership validation in app/routes/tickets.py. The fix adds a single check to ensure that users can only access their own tickets, returning 404 for tickets belonging to other users. All existing tests pass and the vulnerability is resolved.

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.06s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
FAIL - 3 tests, 2 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: Exact HTTP status code and error payload to be used for denied access (403 vs 404).
- Contract ambiguity: Whether the system should mask the existence of the ticket (404) or explicitly deny (403).
- Contract ambiguity: Details of the authentication mechanism (e.g., JWT, session cookie) and how ownership is determined.
- Out of scope (unaddressed): Ticket creation, update, or deletion behavior.
- Out of scope (unaddressed): Authorization rules for admin or privileged roles.
- Out of scope (unaddressed): Non‑ticket related endpoints.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.