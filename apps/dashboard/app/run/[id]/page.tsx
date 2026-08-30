import { notFound } from "next/navigation";
import {
  costLabel,
  decide,
  loadEntries,
  loadEntry,
  mutationScore,
  stopReason,
} from "@/lib/artifacts";
import {
  Card,
  DecisionBadge,
  DegradedNote,
  Diff,
  Field,
  StopReasonNote,
  SuiteColumn,
  VerdictChip,
} from "@/components/ui";

export const dynamic = "force-dynamic";

export async function generateStaticParams() {
  return (await loadEntries()).map((e) => ({ id: e.id }));
}

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const entry = await loadEntry(id);
  if (entry === null) notFound();

  // A pair that raised mid-sweep is not a run with zero passing tests. Render it
  // as what it is and stop, rather than showing empty suites that read as data.
  if (entry.kind === "failed") {
    return (
      <div className="mx-auto max-w-[1240px] px-8 py-12">
        <h1 className="font-mono text-[24px] font-semibold tracking-[-0.02em]">
          {entry.id}
        </h1>
        <div className="mt-4">
          <Card title="Run failed">
            <VerdictChip verdict="invalid" label="NO RESULT" />
            <p className="mt-3 font-mono text-[13px] break-words text-fg-muted">
              {entry.run.error}
            </p>
            <p className="mt-3 text-[12px] text-fg-faint">
              This pair raised before producing a result. It is not a run that
              scored zero — the two are opposite findings. Re-running the sweep
              retries it.
            </p>
          </Card>
        </div>
      </div>
    );
  }

  const r = entry.run;
  const mut = mutationScore(r.mutation);
  const stop = stopReason(r);

  return (
    <div className="mx-auto max-w-[1240px] px-8 py-12">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-mono text-[24px] font-semibold tracking-[-0.02em]">
            {entry.id}
          </h1>
          <p className="t-body mt-2">
            {r.case_id} · {r.mode} ·{" "}
            {r.models.map((m) => `${m.role}=${m.model}`).join(" · ") ||
              "no models recorded"}
          </p>
        </div>
        <DecisionBadge decision={decide(r)} />
      </header>

      <div className="mb-4 flex flex-col gap-2">
        <DegradedNote run={r} />
        <StopReasonNote reason={stop} />
      </div>

      {/* The visual thesis of the project: three suites, fixed order, one row.
          A green visible column beside a red gold column is the whole finding. */}
      <Card
        title="Test suites"
        aside={
          <span className="text-[11px] text-fg-faint">
            visible → verifier → gold
          </span>
        }
        className="mb-4"
      >
        <div className="grid gap-3 md:grid-cols-3">
          <SuiteColumn label="Visible" run={r.visible} emphasis />
          <SuiteColumn
            label="Verifier"
            run={r.verifier}
            note={
              r.verifier === null
                ? r.validity && !r.validity.passed
                  ? `gated invalid — ${r.validity.reason}`
                  : "no verifier test (baseline run)"
                : undefined
            }
          />
          <SuiteColumn label="Gold (hidden)" run={r.gold} emphasis />
        </div>
        {r.visible?.passed && r.gold && !r.gold.passed && (
          <p className="mt-3 rounded-[var(--radius)] border border-fail/40 bg-fail-bg px-3 py-2 text-[12px] text-fail">
            <strong className="font-semibold">Shallow fix.</strong> The visible
            suite passed while the hidden gold suite failed — the patch
            satisfied what it could see and not the behaviour.
          </p>
        )}
      </Card>

      <div className="mb-4 grid gap-4 lg:grid-cols-[1.15fr_1fr]">
        <Card title="Candidate patch">
          <dl className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="files">{r.patch?.files_changed.length ?? 0}</Field>
            <Field label="lines">
              <span className="text-[var(--add)]">
                +{r.patch?.lines_added ?? 0}
              </span>{" "}
              <span className="text-[var(--del)]">
                −{r.patch?.lines_removed ?? 0}
              </span>
            </Field>
            <Field label="edited a test">
              {/* touched_tests means an EXISTING test changed. Adding one is allowed. */}
              {r.patch?.touched_tests ? (
                <span className="text-fail">yes</span>
              ) : (
                <span className="text-fg-muted">no</span>
              )}
            </Field>
            <Field label="stop reason">
              {stop === null ? (
                "—"
              ) : stop === "finished" ? (
                stop
              ) : (
                <span className="text-warn">{stop}</span>
              )}
            </Field>
          </dl>
          {r.patch?.files_changed.length ? (
            <p className="mb-2 scroll-x font-mono text-[12px] whitespace-nowrap text-fg-faint">
              {r.patch.files_changed.join("  ·  ")}
            </p>
          ) : null}
          <Diff diff={r.patch?.diff ?? ""} />
        </Card>

        <div className="flex min-w-0 flex-col gap-4">
          <Card title="Issue contract">
            {r.contract === null ? (
              <p className="text-[13px] text-fg-faint">no contract recorded</p>
            ) : (
              <>
                <div className="mb-3 flex items-center gap-2">
                  <span className="text-[11px] text-fg-faint">confidence</span>
                  <VerdictChip
                    verdict={
                      r.contract.confidence === "high"
                        ? "pass"
                        : r.contract.confidence === "low"
                          ? "invalid"
                          : "none"
                    }
                    label={r.contract.confidence.toUpperCase()}
                  />
                </div>
                <p className="mb-3 text-[13px] leading-relaxed text-fg-muted">
                  {r.contract.summary}
                </p>
                <h3 className="mb-1 text-[11px] tracking-wide text-fg-faint uppercase">
                  Invariants
                </h3>
                <ul className="mb-3 flex list-disc flex-col gap-1 pl-4 text-[13px] text-fg-muted">
                  {r.contract.invariants.map((inv, i) => (
                    <li key={i}>{inv}</li>
                  ))}
                </ul>
                {r.contract.ambiguities.length > 0 && (
                  <>
                    <h3 className="mb-1 text-[11px] tracking-wide text-fg-faint uppercase">
                      Ambiguities ({r.contract.ambiguities.length})
                    </h3>
                    <ul className="flex list-disc flex-col gap-1 pl-4 text-[12px] text-fg-faint">
                      {r.contract.ambiguities.map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
          </Card>

          <Card title="Independent verifier test">
            {r.verifier_test === null ? (
              <p className="text-[13px] text-fg-faint">
                no verifier test — baseline runs have no independent oracle
              </p>
            ) : (
              <>
                <Field label="file">{r.verifier_test.filename}</Field>
                <p className="mt-2 mb-3 text-[13px] leading-relaxed text-fg-muted">
                  {r.verifier_test.invariant}
                </p>
                {r.validity && (
                  <div className="rounded-[var(--radius)] bg-surface-2 p-2.5">
                    <div className="mb-1.5 flex items-center gap-2">
                      <VerdictChip
                        verdict={r.validity.passed ? "pass" : "invalid"}
                      />
                      <span className="font-mono text-[11px] text-fg-faint">
                        compiles={String(r.validity.compiles)} runs=
                        {String(r.validity.runs)} fails_on_bug=
                        {String(r.validity.fails_on_original_bug)}
                      </span>
                    </div>
                    <p className="text-[12px] text-fg-muted">
                      {r.validity.reason}
                    </p>
                  </div>
                )}
              </>
            )}
          </Card>
        </div>
      </div>

      <Card
        title="Mutation sensitivity"
        aside={
          mut.denominator > 0 ? (
            <span className="font-mono text-[12px]">
              {mut.killed} / {mut.denominator} killed
            </span>
          ) : (
            <span className="text-[11px] text-fg-faint">not scored</span>
          )
        }
        className="mb-4"
      >
        {r.mutation.length === 0 ? (
          <p className="text-[13px] text-fg-faint">
            No mutants scored. Baseline runs do not produce a verifier test to
            score.
          </p>
        ) : (
          <>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {r.mutation.map((m) => (
                <div
                  key={m.mutant_id}
                  className={`rounded-[var(--radius)] border p-2.5 ${
                    m.scored
                      ? "border-border bg-surface-2"
                      : "border-dashed border-border-strong bg-none-bg"
                  }`}
                >
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-mono text-[12px]">{m.mutant_id}</span>
                    {m.scored ? (
                      <VerdictChip
                        verdict={m.killed ? "pass" : "fail"}
                        label={m.killed ? "KILLED" : "SURVIVED"}
                      />
                    ) : (
                      <VerdictChip verdict="none" label="EXCLUDED" />
                    )}
                  </div>
                  <p className="text-[12px] leading-snug text-fg-muted">
                    {m.description}
                  </p>
                  {!m.scored && (
                    <p className="mt-1 text-[11px] text-fg-faint">
                      No in-process test can kill this mutant, so it is kept out
                      of the denominator.
                    </p>
                  )}
                </div>
              ))}
            </div>
            {mut.excluded.length > 0 && (
              <p className="mt-3 text-[12px] text-fg-faint">
                Score is over scored mutants only ({mut.excluded.join(", ")}{" "}
                excluded), matching mutation_results.json.
              </p>
            )}
          </>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Visible suite output">
          <pre className="scroll-x max-h-80 overflow-y-auto rounded-[var(--radius)] bg-surface-2 p-3 font-mono text-[12px] leading-[1.5] text-fg-muted">
            {r.visible?.stdout_tail?.trim() || "no output"}
          </pre>
        </Card>
        <Card title="Review packet">
          <pre className="scroll-x max-h-80 overflow-y-auto rounded-[var(--radius)] bg-surface-2 p-3 font-mono text-[12px] leading-[1.5] whitespace-pre-wrap text-fg-muted">
            {entry.packet ?? "no review_packet.md in this artifact directory"}
          </pre>
        </Card>
      </div>

      <p className="mt-4 text-[12px] text-fg-faint">
        Runtime {r.runtime_sec.toFixed(1)}s · model cost {costLabel(r)} ·
        SplitSpec merged nothing and approves nothing on its own; every decision
        here is for a human to review.
      </p>
    </div>
  );
}
