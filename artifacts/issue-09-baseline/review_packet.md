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

- Out of scope: UI rendering details, deployment processes, and any background jobs unrelated to the event‑listing endpoint.

## Behavioral invariant
None captured — the contract was not produced (or was unreadable).
## Candidate patch
- Files changed: app/routes/events.py, visible_tests/issue-09/test_cache_invalidation.py, visible_tests/issue-09/test_comprehensive_cache.py, visible_tests/issue-09/test_event_list_caching.py, visible_tests/issue-09/test_event_list_consistency.py
- Patch size: +282/-0 lines
- Stop reason: finished
- Patch notes: stop_reason=finished; Fixed issue where newly created events sometimes don't show up in the event list immediately. The problem was that the cache was not being invalidated after event creation, causing subsequent requests to return stale cached data. **Changes made:** - Modified `app/routes/events.py`: Added `request.app.state.cache.invalidate()` after committing a new event in the `create_event` function **Tests created:** - `test_event_list_caching.py`: Verifies newly created events appear in cached event lists - `test_cache_invalidation.py`: Tests cache invalidation with multiple events and pagination - `test_c... [truncated, 997 chars; full reply in trajectory.jsonl]

## Visible tests
PASS - 3 tests, 0 failed, 0 errors
```
...                                                                      [100%]
3 passed in 0.05s
```

## Independent verifier test
n/a
- Validity: no validity gate recorded (test never earned the right to grade)

## Gold hidden evaluator
PASS - 3 tests, 0 failed, 0 errors

## Mutation sensitivity
no mutants scored (baseline run, or none applicable)

## Residual risks
- Contract ambiguity: No concrete steps to reliably reproduce the issue are provided.
- Contract ambiguity: It is unclear whether the list endpoint is expected to be strongly consistent or eventually consistent.
- Contract ambiguity: Timing expectations (how soon after creation the event must appear) are not defined.
- Contract ambiguity: Details about pagination, filtering, or caching layers that might affect visibility are missing.
- Contract ambiguity: No information about the environment (development, staging, production) or specific request/response data is given.
- Out of scope (unaddressed): UI rendering details, deployment processes, and any background jobs unrelated to the event‑listing endpoint.

- Independence note: fixer and verifier run on different models
- Model cost is not measured in this build (the agent loops drop token usage), so no cost is reported here.
- This is advisory evidence, not an approval. A human must review it.

## Human action
Review the evidence in this packet and either approve or reject the patch. Judge the patch against the gold hidden evaluator's result, the verifier's independence note, and the mutation sensitivity before deciding.

SplitSpec merged nothing and approves nothing on its own — every decision above is
recommendation only, and a human must review the evidence before any merge or deploy.