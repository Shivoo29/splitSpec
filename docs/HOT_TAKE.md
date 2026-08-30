# Hot take: a mocked client validates nothing about a provider

**The failure mode:** every module in this project passed its own full test suite
while carrying a live bug that only appeared against a real model provider.

Not one module. Every module that touched the network. The unit suites were not
weak — they were thorough, they were written test-first, and they were green. They
were also, in the part that mattered, testing a `FakeClient` that accepted any
transcript, any message ordering, and any token budget we handed it. The suite
proved our code was internally consistent. It could not prove the thing we
actually needed, which is that a provider on the other end of an HTTP connection
would accept what we sent.

## The receipts

Ten bugs, each invisible to a green test suite, each found only by making a real
call. The full table with symptoms and causes is in `docs/MODULES.md`; these are
the ones that changed how we build:

| What the tests said | What the provider did |
|---|---|
| Contract parsing works | Model wrapped its JSON in ```` ```json ```` fences regardless of instructions |
| Model returns non-JSON, must handle it | The reply was **truncated**, not malformed. We had built error handling for a failure that wasn't happening |
| Agent loop drives a conversation | The assistant turn was never appended. Every real run would have 400'd on turn two |
| Budget caps the run | `max_tokens` was set to the whole run budget, so the provider rejected it with HTTP 413 |
| Model id is configured | Mistral answered a request for a retired id with **HTTP 200 served by a different model** — not a 404 |
| Agent stopped on budget | The budget summed resent context every turn, so it charged the same 19k transcript 22 times to "use" 205k of 200k |

The fifth is the one that should worry anyone building an eval harness. We asked
for `devstral-small-latest`. The provider silently substituted
`mistral-medium-3-5` and returned success. Every run would have completed, every
number would have looked fine, and the result table would have named a model that
never ran. In a project whose entire output is a comparison *between models*, a
mislabelled row is worse than a missing one — and nothing in a green test suite
would ever have caught it.

## Why this happens

A mock encodes what you *believe* the interface is. That belief is exactly the
thing under test, and the mock is built from the same misunderstanding as the
code. So the mock agrees with the code, the test passes, and the misunderstanding
survives. The tighter the mock matches your mental model, the more confidently it
confirms your error.

This is the same structural problem SplitSpec was built to study, one level up. A
fixer agent that writes its own tests will write tests that agree with its own
misreading of the issue. We caught the agent version of this and then spent a week
committing the developer version of it in our own repo.

## What we changed

- **Every module ships a live check**, not just a unit suite. `scripts/live_check_verifier.py`
  exists because the verifier's unit tests could not have told us whether a real
  model produces a test that compiles.
- **The run preflights model ids** against `GET /models` and refuses to start on a
  mismatch, because a silent substitution completes successfully and corrupts the
  result quietly.
- **Missing data is `None` with a stated reason, never `0`.** A zero and an
  unmeasured value are opposite findings; conflating them turns a broken pipeline
  into a plausible-looking number.
- **Parse outcomes, never exit codes.** A test that fails to import has not caught
  a bug. pytest returns non-zero for both.

## What we would do differently

Write the live check *first*, against the real provider, before the unit suite —
one call, one assertion, no mock. It takes ten minutes and it fixes the interface
you are about to mock. Then mock freely: the mock is now built from an observation
instead of an assumption, and the unit suite starts being worth what it costs.

For anyone building agent evaluation specifically: **verify that the model you
asked for is the model that answered.** Check the `model` field on the response
against the one you sent. It is two lines, and without it your comparison between
models is unfalsifiable.
