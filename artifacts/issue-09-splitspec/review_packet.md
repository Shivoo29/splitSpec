# SplitSpec Review Packet — Issue issue-09

## Decision
ESCALATE

Decision inputs:
- Contract confidence: low
- Expect escalation (case rule): False
- Visible tests: PASS (ran: True)
- Verifier test: n/a (valid: False; ran: False)
- Patch edited an existing test: False

## Issue
Newly created events sometimes do not show up in the event list

We added an event this morning and it did not appear on the events page.
Reloading did not help. It showed up eventually - I think after we
redeployed. The event definitely existed, because opening its direct link
worked fine the whole time. It seems to happen more on the pages we look at
most often during the day.

- Out of scope: Deployment processes, UI rendering performance, unrelated API endpoints, and any external caching layers not directly tied to the events listing.

## Behavioral invariant
None captured — the contract was not produced (or was unreadable).
## Candidate patch
- Files changed: app/routes/events.py, visible_tests/issue-09/test_comprehensive_cache.py, visible_tests/issue-09/test_event_list_cache.py, visible_tests/issue-09/test_event_list_cache_invalidation.py
- Patch size: +139/-0 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; ## Summary **Problem Identified**: Newly created events were not appearing in the event list due to a caching issue. The event list was cached but the cache was not being invalidated when new events were created. **Root Cause**: In `app/routes/events.py`, the `create_event` function was creating events and committing them to the database, but it wasn't calling `request.app.state.cache.invalidate()` to clear the cached event list. **Solution**: Added a single line `request.app.state.cache.invalidate()` in the `create_event` function after `session.commit()` to ensure the cache is cleared when n... [truncated, 1357 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.05s
```

## Independent verifier test
n/a
- Invariant: Any successfully created event must be immediately visible in the events listing endpoint.
- Assumptions:
  - The API endpoint '/events' does not intentionally employ a delay or eventual consistency mechanism that would naturally cause a newly created item to be missing.
  - The 'events' listing does not perform complex filtering that would exclude the newly created event (e.g., date filtering).
  - The application environment used for testing does not have an external persistent cache (like Redis) that requires manual invalidation that the test cannot control.
- Validity: invalid/gated (compiles=True, runs=True, fails_on_original_bug=False) — test passed on buggy code (0 failed, 0 errors), so it is not discriminating

## Gold hidden evaluator
PASS - 3 tests, 0 failed, 0 errors

## Mutation sensitivity
Detected 0/4 incorrect variants
- Killed: 0/4

## Residual risks
- Contract ambiguity: How the event is created (API endpoint, request payload, authentication).
- Contract ambiguity: The exact timing between event creation and the request for the events list.
- Contract ambiguity: Whether any caching (in‑memory, Redis, CDN) is involved for the events list.
- Contract ambiguity: Database transaction semantics or eventual consistency guarantees.
- Contract ambiguity: Environment details (development vs production, single vs multiple instances).
- Contract ambiguity: Reproducibility steps: no deterministic steps are provided to reliably trigger the issue.
- Out of scope (unaddressed): Deployment processes, UI rendering performance, unrelated API endpoints, and any external caching layers not directly tied to the events listing.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.