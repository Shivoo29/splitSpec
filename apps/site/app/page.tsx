import { loadResults } from "@/lib/results";

const REPO = "https://github.com/Shivoo29/splitSpec";

function Section({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-[980px] px-6 py-16 md:py-20">
      <p className="t-section mb-3">{eyebrow}</p>
      <h2 className="t-display mb-6 max-w-[20ch]">{title}</h2>
      {children}
    </section>
  );
}

function Stat({ value, label, note }: { value: string; label: string; note?: string }) {
  return (
    <div className="rounded-[var(--radius)] border border-border bg-surface p-6">
      <p className="t-figure">{value}</p>
      <p className="mt-2 text-[14px] font-medium">{label}</p>
      {note && <p className="t-caption mt-1">{note}</p>}
    </div>
  );
}

export default async function Home() {
  const r = await loadResults();
  const total = r.baselineRuns + r.splitspecRuns;

  return (
    <div id="top">
      {/* Hero. One claim, stated as the mechanism rather than a benefit - the
          mechanism is what is actually proven, and it is the interesting part. */}
      <section className="mx-auto max-w-[980px] px-6 pt-20 pb-10 md:pt-28">
        <p className="t-section mb-4">Independent verification for AI-generated bug fixes</p>
        <h1 className="t-display max-w-[16ch] text-[clamp(2.25rem,1.4rem+3vw,3.75rem)]">
          The agent that writes the fix never sees the test that grades the fix.
        </h1>
        <p className="t-body mt-6 max-w-[60ch] text-[17px]">
          A coding agent stops when the visible tests go green, so a shallow fix and a real one
          arrive looking identical. SplitSpec has a second agent — isolated from the first, working
          only from the issue and the pre-patch code — write the test that decides.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          <Stat
            value={`${r.reviewsBaseline} → ${r.reviewsSplitspec}`}
            label="Patches needing a human"
            note={`across ${r.splitspecRuns} measured runs`}
          />
          <Stat
            value={`${r.cleared}/${r.correct}`}
            label="Correct patches auto-cleared"
            note="zero false rejections"
          />
          <Stat
            value={`${r.brokenCleared}/${r.broken}`}
            label="Broken patch cleared anyway"
            note="the miss, reported below"
          />
        </div>
      </section>

      <Section eyebrow="The problem" title="Review is now the bottleneck, not writing.">
        <div className="t-body max-w-[62ch] space-y-4">
          <p>
            96% of developers say they do not fully trust AI-generated code without checking it, yet
            adoption sits near 84%. The work moved from writing to verifying, and verification did
            not get faster.
          </p>
          <p>
            Agentic pull requests take 5.3× longer to pick up, review time is up 91% on teams with
            heavy AI use, and AI-authored PRs sit unclaimed 4.6× longer than human ones. In one
            study of 6,080 AI-generated CVE patches,{" "}
            <strong className="font-semibold text-fg">53.9% were flawed</strong>.
          </p>
          <p>
            The reason is structural: the agent that writes the patch also decides it is done. It
            stops when the visible suite passes. Nothing in that loop can tell{" "}
            <em>fixed</em> from <em>looks fixed</em>.
          </p>
        </div>
      </Section>

      <Section eyebrow="How it works" title="The boundary is structural, not prompted.">
        <div className="scroll-x rounded-[var(--radius)] border border-border bg-surface">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="t-section">
                <th className="px-5 py-3.5 font-[590]">Stage</th>
                <th className="px-5 py-3.5 font-[590]">Sees</th>
                <th className="px-5 py-3.5 font-[590]">Never sees</th>
              </tr>
            </thead>
            <tbody className="text-[14px]">
              {[
                ["Contract builder", "The issue text, a file listing", "The patch, any test"],
                [
                  "Fixer",
                  "The contract, the pre-patch repo, the visible tests",
                  "The verifier's test, the gold tests",
                ],
                [
                  "Verifier",
                  "The contract, the pre-patch repo",
                  "The patch, the fixer's workspace, the gold tests",
                ],
                ["Judge", "The patch, all three suites", "— calls no model, infers nothing"],
              ].map(([stage, sees, never]) => (
                <tr key={stage} className="border-t border-border align-top">
                  <td className="px-5 py-3.5 font-medium">{stage}</td>
                  <td className="px-5 py-3.5 text-fg-muted">{sees}</td>
                  <td className="px-5 py-3.5 text-fg-muted">{never}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="t-body mt-6 max-w-[62ch]">
          Each agent runs in its own materialised workspace and asserts at entry that the other&apos;s
          artifacts are unreachable. The verifier&apos;s test is hashed and frozen before any patch is
          judged, then re-hashed before it is allowed to grade. A generated test must also{" "}
          <strong className="font-semibold text-fg">fail on the original buggy code</strong> before
          it may decide anything — a test that passes on the bug would never have caught a shallow
          fix.
        </p>
      </Section>

      <Section eyebrow="Results" title="What the measurement actually showed.">
        <div className="scroll-x rounded-[var(--radius)] border border-border bg-surface">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="t-section">
                <th className="px-5 py-3.5 font-[590]">Metric</th>
                <th className="px-5 py-3.5 font-[590]">Baseline</th>
                <th className="px-5 py-3.5 font-[590]">SplitSpec</th>
              </tr>
            </thead>
            <tbody className="text-[14px]">
              {[
                ["Correct patches auto-cleared", `0 / ${r.correct}`, `${r.cleared} / ${r.correct}`],
                ["False rejections", "0", "0"],
                ["Broken patches cleared", "0", `${r.brokenCleared}`],
                ["Human reviews required", `${r.reviewsBaseline}`, `${r.reviewsSplitspec}`],
                [
                  "Median runtime per issue",
                  `${Math.round(r.medianBaseline)}s`,
                  `${Math.round(r.medianSplitspec)}s`,
                ],
              ].map(([metric, base, split]) => (
                <tr key={metric} className="border-t border-border">
                  <td className="px-5 py-3.5">{metric}</td>
                  <td className="px-5 py-3.5 font-mono text-fg-muted">{base}</td>
                  <td className="px-5 py-3.5 font-mono font-medium">{split}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="t-caption mt-4">
          {total} completed runs across 12 seeded cases; {r.incomplete} pairs failed on provider
          timeouts and are excluded. Generated test validity {r.validityValid}/{r.validityTotal};
          mutation score {r.mutantsKilled}/{r.mutantsTotal}.
        </p>

        {/* The miss gets its own block, at full weight. A page that buries it is
            the same failure mode the project exists to study. */}
        <div className="mt-10 rounded-[var(--radius)] border border-fail/30 bg-fail-bg p-6">
          <p className="t-section mb-2 text-fail">Where it failed</p>
          <p className="max-w-[62ch] text-[15px] leading-relaxed text-fail">
            On one case the verifier wrote a valid, mutation-killing test that{" "}
            <strong className="font-semibold">passed on a broken patch</strong>, turning a cautious
            REVIEW REQUIRED into a confident ACCEPT. False-fix detection recall is {" "}
            {r.brokenCleared === 0 ? "1 / 1" : `0 / ${r.broken}`} — one case is not a rate, and the
            oracle-strength question is unresolved rather than answered.
          </p>
          <p className="mt-3 max-w-[62ch] text-[14px] leading-relaxed text-fail/90">
            Published work predicts this: 80.2% of agent-authored test patches carry weak or no
            oracle signal, and strong-oracle rates range from 18% to 67% by model. The verifier here
            is a small, fast model at the low end of that range.
          </p>
        </div>
      </Section>

      <Section eyebrow="Honest scope" title="What this is, and what it is not.">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-[var(--radius)] border border-border bg-surface p-6">
            <p className="mb-3 text-[15px] font-semibold">Measured</p>
            <ul className="t-body space-y-2 text-[14px]">
              <li>Gold suites validated in both directions across all 12 cases</li>
              <li>The validity gate rejects tests that pass on the bug, automatically</li>
              <li>Generated tests kill known-incorrect variants</li>
              <li>Verification adds ~2 minutes of machine time per patch</li>
            </ul>
          </div>
          <div className="rounded-[var(--radius)] border border-border bg-surface p-6">
            <p className="mb-3 text-[15px] font-semibold">Not claimed</p>
            <ul className="t-body space-y-2 text-[14px]">
              <li>That it generalises to other repositories</li>
              <li>That it replaces code review or guarantees correctness</li>
              <li>That the verifier reliably catches shallow fixes</li>
              <li>Anything about models other than the three documented</li>
            </ul>
          </div>
        </div>
        <p className="t-body mt-8 max-w-[62ch]">
          Every figure on this page is read at build time from the run artifacts committed to the
          repository. You can recompute all of them in about two seconds, with no API keys:
        </p>
        <pre className="scroll-x mt-4 rounded-[var(--radius-sm)] border border-border bg-surface-2 p-4 font-mono text-[13px] leading-relaxed">
          {`git clone ${REPO}
pip install -r requirements.txt
python -m splitspec.report --from artifacts/`}
        </pre>
      </Section>
    </div>
  );
}
