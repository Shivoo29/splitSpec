import Link from "next/link";
import {
  loadEntries,
  stopReason,
  type Entry,
  type RunResult,
} from "@/lib/artifacts";
import { Card, VerdictChip } from "@/components/ui";

/** A rate is only reportable with its denominator, and only over runs that were
 *  actually measured. Missing data is null with a reason, never 0 — a zero and an
 *  unmeasured value are opposite findings. */
function rate(numerator: number, denominator: number, reason: string) {
  if (denominator === 0) return { label: "not measured", detail: reason };
  return {
    label: `${((numerator / denominator) * 100).toFixed(0)}%`,
    detail: `${numerator} of ${denominator}`,
  };
}

function runsOf(entries: Entry[], mode: RunResult["mode"]): RunResult[] {
  return entries
    .filter((e): e is Extract<Entry, { kind: "run" }> => e.kind === "run")
    .map((e) => e.run)
    .filter((r) => r.mode === mode && !r.degraded);
}

export default async function ComparePage() {
  const entries = await loadEntries();
  const modes: RunResult["mode"][] = ["baseline", "splitspec"];

  const rows = modes.map((mode) => {
    const runs = runsOf(entries, mode);

    // The gold oracle is the ground truth column: what a perfect hidden suite saw.
    const goldCaught = runs.filter((r) => r.gold && !r.gold.passed).length;
    const goldScored = runs.filter((r) => r.gold !== null).length;

    // What the system itself caught, using only what it was allowed to see.
    const shallow = runs.filter(
      (r) => r.visible?.passed && r.gold && !r.gold.passed,
    );
    const caught = shallow.filter(
      (r) => r.verifier && !r.verifier.passed,
    ).length;

    const gated = runs.filter((r) => r.validity !== null);
    const valid = gated.filter((r) => r.validity!.passed).length;

    const truncated = runs.filter((r) => {
      const s = stopReason(r);
      return s !== null && s !== "finished";
    }).length;

    const runtimes = runs.map((r) => r.runtime_sec).sort((a, b) => a - b);
    const median =
      runtimes.length === 0
        ? null
        : runtimes.length % 2
          ? runtimes[(runtimes.length - 1) / 2]
          : (runtimes[runtimes.length / 2 - 1] +
              runtimes[runtimes.length / 2]) /
            2;

    return {
      mode,
      runs: runs.length,
      recall: rate(
        caught,
        shallow.length,
        "no run yet where visible passed, gold failed, and a verifier test graded it",
      ),
      validity: rate(
        valid,
        gated.length,
        "no verifier test has been through the validity gate",
      ),
      goldCatch: rate(goldCaught, goldScored, "no run has a gold suite result"),
      truncated: `${truncated} / ${runs.length}`,
      median: median === null ? "not measured" : `${median.toFixed(1)}s`,
    };
  });

  return (
    <div className="mx-auto max-w-[1120px] px-6 py-12">
      <header className="rise mb-10">
        <h1 className="t-display">Baseline vs SplitSpec vs gold oracle</h1>
        <p className="t-body mt-2">
          Degraded runs are excluded from every figure. A cell reading{" "}
          <span className="font-mono">not measured</span> has no data behind it
          — it is not a zero.
        </p>
      </header>

      <Card className="mb-4">
        <div className="scroll-x">
          <table className="w-full min-w-[860px] border-collapse text-left">
            <thead>
              <tr className="text-[11px] tracking-wide text-fg-faint uppercase">
                <th className="pb-2 pr-4 font-medium">Mode</th>
                <th className="pb-2 pr-4 font-medium">Runs</th>
                <th className="pb-2 pr-4 font-medium">
                  False-fix detection recall
                </th>
                <th className="pb-2 pr-4 font-medium">
                  Generated test validity
                </th>
                <th className="pb-2 pr-4 font-medium">Gold caught the bug</th>
                <th className="pb-2 pr-4 font-medium">Truncated</th>
                <th className="pb-2 font-medium">Median runtime</th>
              </tr>
            </thead>
            <tbody className="font-mono text-[13px]">
              {rows.map((row) => (
                <tr key={row.mode} className="border-t border-border align-top">
                  <td className="py-2.5 pr-4">{row.mode}</td>
                  <td className="py-2.5 pr-4">{row.runs}</td>
                  {[row.recall, row.validity, row.goldCatch].map((cell, i) => (
                    <td key={i} className="py-2.5 pr-4">
                      <span
                        className={
                          cell.label === "not measured" ? "text-fg-faint" : ""
                        }
                      >
                        {cell.label}
                      </span>
                      <span className="block text-[11px] text-fg-faint">
                        {cell.detail}
                      </span>
                    </td>
                  ))}
                  <td className="py-2.5 pr-4">{row.truncated}</td>
                  <td className="py-2.5">{row.median}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Per-run detail">
        <div className="scroll-x">
          <table className="w-full min-w-[720px] border-collapse text-left">
            <thead>
              <tr className="text-[11px] tracking-wide text-fg-faint uppercase">
                <th className="pb-2 pr-4 font-medium">Run</th>
                <th className="pb-2 pr-4 font-medium">Visible</th>
                <th className="pb-2 pr-4 font-medium">Verifier</th>
                <th className="pb-2 pr-4 font-medium">Gold</th>
                <th className="pb-2 font-medium">Reading</th>
              </tr>
            </thead>
            <tbody className="font-mono text-[13px]">
              {entries.map((entry) => {
                if (entry.kind === "failed") {
                  return (
                    <tr key={entry.id} className="border-t border-border">
                      <td className="py-2 pr-4">
                        <Link
                          href={`/runs/${entry.id}`}
                          className="hover:text-accent"
                        >
                          {entry.id}
                        </Link>
                      </td>
                      <td className="py-2 pr-4" colSpan={4}>
                        <VerdictChip verdict="invalid" label="RUN FAILED" />
                      </td>
                    </tr>
                  );
                }
                const r = entry.run;
                const shallow = r.visible?.passed && r.gold && !r.gold.passed;
                return (
                  <tr key={entry.id} className="border-t border-border">
                    <td className="py-2 pr-4">
                      <Link
                        href={`/runs/${entry.id}`}
                        className="hover:text-accent"
                      >
                        {entry.id}
                      </Link>
                    </td>
                    <td className="py-2 pr-4">
                      <VerdictChip
                        verdict={
                          r.visible
                            ? r.visible.passed
                              ? "pass"
                              : "fail"
                            : "none"
                        }
                      />
                    </td>
                    <td className="py-2 pr-4">
                      <VerdictChip
                        verdict={
                          r.verifier
                            ? r.verifier.passed
                              ? "pass"
                              : "fail"
                            : r.validity && !r.validity.passed
                              ? "invalid"
                              : "none"
                        }
                      />
                    </td>
                    <td className="py-2 pr-4">
                      <VerdictChip
                        verdict={
                          r.gold ? (r.gold.passed ? "pass" : "fail") : "none"
                        }
                      />
                    </td>
                    <td className="py-2 text-[12px] text-fg-muted">
                      {shallow
                        ? "shallow fix: visible passed, gold failed"
                        : r.gold?.passed
                          ? "gold passed: the behaviour holds"
                          : "patch rejected before gold could matter"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
