import Link from "next/link";
import {
  costLabel,
  decide,
  loadEntries,
  stopReason,
  type Entry,
} from "@/lib/artifacts";
import { Card, DecisionBadge, VerdictChip } from "@/components/ui";

export const dynamic = "force-dynamic";

function groupByCase(entries: Entry[]) {
  const map = new Map<string, Entry[]>();
  for (const e of entries) {
    const list = map.get(e.run.case_id) ?? [];
    list.push(e);
    map.set(e.run.case_id, list);
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export default async function Home() {
  const entries = await loadEntries();
  const runs = entries.filter((e) => e.kind === "run");
  const grouped = groupByCase(entries);

  // Every headline figure carries its denominator. A rate without one is not a
  // finding, and this page is the first place a reader would forget that.
  const shallow = runs.filter(
    (e) =>
      e.kind === "run" &&
      e.run.visible?.passed &&
      e.run.gold &&
      !e.run.gold.passed,
  ).length;
  const truncated = runs.filter(
    (e) =>
      e.kind === "run" &&
      stopReason(e.run) !== null &&
      stopReason(e.run) !== "finished",
  ).length;

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold tracking-tight">Run overview</h1>
        <p className="mt-0.5 text-[13px] text-fg-muted">
          Every figure below is shown against the number of runs it was computed
          over.
        </p>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card title="Runs on disk">
          <p className="font-mono text-2xl">{entries.length}</p>
          <p className="mt-1 text-[11px] text-fg-faint">
            {entries.length - runs.length} failed before producing a result
          </p>
        </Card>
        <Card title="Shallow fixes">
          <p className="font-mono text-2xl">
            {shallow}
            <span className="text-fg-faint"> / {runs.length}</span>
          </p>
          <p className="mt-1 text-[11px] text-fg-faint">
            visible passed, gold failed
          </p>
        </Card>
        <Card title="Truncated attempts">
          <p className="font-mono text-2xl">
            {truncated}
            <span className="text-fg-faint"> / {runs.length}</span>
          </p>
          <p className="mt-1 text-[11px] text-fg-faint">
            agent stopped before finishing
          </p>
        </Card>
        <Card title="Model cost">
          <p className="font-mono text-2xl text-fg-faint">not measured</p>
          <p className="mt-1 text-[11px] text-fg-faint">
            agents drop token usage before it reaches the result
          </p>
        </Card>
      </div>

      {grouped.length === 0 && (
        <Card>
          <p className="text-[13px] text-fg-muted">
            No runs found in <code className="font-mono">artifacts/</code>.
            Produce one with{" "}
            <code className="font-mono text-fg">
              python -m splitspec.run --mode baseline --case cases/issue-07.yaml
              --output artifacts/issue-07-baseline
            </code>
            .
          </p>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {grouped.map(([caseId, group]) => (
          <Card
            key={caseId}
            title={caseId}
            aside={
              <span className="text-[11px] text-fg-faint">
                {group.length} run(s)
              </span>
            }
          >
            <div className="scroll-x">
              <table className="w-full min-w-[840px] border-collapse text-left">
                <thead>
                  <tr className="text-[11px] tracking-wide text-fg-faint uppercase">
                    <th className="pb-2 pr-3 font-medium">Run</th>
                    <th className="pb-2 pr-3 font-medium">Mode</th>
                    <th className="pb-2 pr-3 font-medium">Decision</th>
                    <th className="pb-2 pr-3 font-medium">Visible</th>
                    <th className="pb-2 pr-3 font-medium">Verifier</th>
                    <th className="pb-2 pr-3 font-medium">Gold</th>
                    <th className="pb-2 pr-3 font-medium">Stop</th>
                    <th className="pb-2 font-medium">Cost</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-[13px]">
                  {group.map((entry) => {
                    if (entry.kind === "failed") {
                      return (
                        <tr key={entry.id} className="border-t border-border">
                          <td className="py-2 pr-3">
                            <Link
                              href={`/run/${entry.id}`}
                              className="hover:text-accent"
                            >
                              {entry.id}
                            </Link>
                          </td>
                          <td className="py-2 pr-3">{entry.run.mode}</td>
                          <td className="py-2 pr-3" colSpan={6}>
                            <VerdictChip verdict="invalid" label="RUN FAILED" />
                            <span className="ml-2 text-fg-muted">
                              {entry.run.error}
                            </span>
                          </td>
                        </tr>
                      );
                    }
                    const r = entry.run;
                    const stop = stopReason(r);
                    return (
                      <tr key={entry.id} className="border-t border-border">
                        <td className="py-2 pr-3">
                          <Link
                            href={`/run/${entry.id}`}
                            className="hover:text-accent"
                          >
                            {entry.id}
                          </Link>
                        </td>
                        <td className="py-2 pr-3 text-fg-muted">{r.mode}</td>
                        <td className="py-2 pr-3">
                          <DecisionBadge decision={decide(r)} />
                        </td>
                        <td className="py-2 pr-3">
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
                        <td className="py-2 pr-3">
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
                        <td className="py-2 pr-3">
                          <VerdictChip
                            verdict={
                              r.gold
                                ? r.gold.passed
                                  ? "pass"
                                  : "fail"
                                : "none"
                            }
                          />
                        </td>
                        <td className="py-2 pr-3 text-fg-muted">
                          {stop === null ? (
                            "—"
                          ) : stop === "finished" ? (
                            "finished"
                          ) : (
                            <span className="text-warn">{stop}</span>
                          )}
                        </td>
                        <td className="py-2 text-fg-faint">{costLabel(r)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
