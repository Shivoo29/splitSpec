# SplitSpec — site

One app: the story, the run evidence, and the comparison. Fully static, so it
deploys anywhere with no server and no credentials.

```bash
npm install
npm run dev      # http://localhost:4500
npm run build    # emits ./out
```

## Routes

| Route | What it is |
|---|---|
| `/` | The problem, the mechanism, the measured result |
| `/runs` | Every run grouped by case |
| `/runs/[id]` | One run: contract, patch, frozen verifier test, the three suites, mutation grid, packet |
| `/compare` | Baseline vs SplitSpec vs the gold oracle |

## Deploying

Every figure is read from `artifacts/**/result.json` **at build time**, so the
numbers are frozen with the commit that produced them and there is nothing to run
at request time.

**Vercel:** point it at this repo, set the root directory to `apps/site`. The
build reads `../../artifacts`, so the whole repo must be checked out (it is, by
default).

**GitHub Pages / Netlify / any static host:** `npm run build`, publish `out/`.

If a number here is wrong, the run that produced it is wrong - the page has no
hand-written figures. Re-run the sweep, rebuild, and it updates.
