# SplitSpec evidence dashboard

Read-only viewer over `artifacts/**/result.json`. Module 12.

```bash
npm install
npm run dev     # http://localhost:4400
```

**Local-only tool. Do not expose it.** It reads the repository's artifact
directory from disk on every request, has no authentication, and is not written
to be reachable by anyone but the person running the sweep.

## What it shows

- `/` — runs grouped by case, with the three suite outcomes at a glance
- `/run/[id]` — contract, patch diff, frozen verifier test, the three suites in
  fixed order (visible → verifier → gold), the mutation grid, the review packet
- `/compare` — baseline vs splitspec vs the gold oracle

## Reading the screen

Four things are easy to misread, so the UI states them explicitly:

- **`not measured` is not zero.** Model cost is unmeasured in every run today
  (the agents drop token usage before it reaches `RunResult`), so it never
  renders as `$0.00`. A rate with no data behind it says `not measured` rather
  than `0%`.
- **A failed run is not a run that scored zero.** A pair that raised mid-sweep
  writes `{ok: false, error}` and renders as `RUN FAILED`, never as empty suites.
- **`edited a test` means an *existing* test changed.** Adding a test is
  permitted and is not flagged.
- **Excluded mutants are out of the denominator.** A mutant no in-process test
  can kill is shown in the grid marked `EXCLUDED`; the score is computed over the
  rest, matching `mutation_results.json`.

A `budget` stop reason is surfaced on every run that has one: that patch is a
truncated attempt, and reading it as a finished one overstates the failure.
