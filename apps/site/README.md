# SplitSpec site

Static landing page for the project. Every figure is read from
`artifacts/**/result.json` **at build time**, so the numbers are the measured ones
and the output is still a plain static site with no server.

```bash
npm install
npm run dev      # http://localhost:4500
npm run build    # emits ./out
```

Deploy `out/` to any static host (GitHub Pages, Vercel, Netlify). Nothing runs at
request time and there are no credentials.

If a number here is wrong, the run that produced it is wrong - the page has no
hand-written figures. Re-run the sweep, rebuild, and it updates.

Shares `app/globals.css` with `apps/dashboard`: one set of colour tokens, one type
scale, one motion token. Keep them in sync by copying, not by diverging.
