import type { ReactNode } from "react";
import type { RunResult, TestRun, Verdict } from "@/lib/artifacts";

/* Inline SVG only - no emoji anywhere in the UI. Each verdict pairs a colour with
   a distinct glyph AND a word, so the meaning survives greyscale, colour-blind
   vision, and a printed page. */

function Glyph({ verdict }: { verdict: Verdict }) {
  const common = {
    width: 14,
    height: 14,
    viewBox: "0 0 16 16",
    "aria-hidden": true,
  } as const;
  if (verdict === "pass")
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="2.2">
        <path
          d="M3 8.5l3.2 3.2L13 5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  if (verdict === "fail")
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="2.2">
        <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
      </svg>
    );
  if (verdict === "invalid")
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="2.2">
        <circle cx="8" cy="8" r="5.6" />
        <path d="M4.2 11.8L11.8 4.2" strokeLinecap="round" />
      </svg>
    );
  return (
    <svg {...common} fill="none" stroke="currentColor" strokeWidth="2.2">
      <path d="M4 8h8" strokeLinecap="round" />
    </svg>
  );
}

const VERDICT_STYLE: Record<Verdict, string> = {
  pass: "text-pass bg-pass-bg border-pass/35",
  fail: "text-fail bg-fail-bg border-fail/35",
  invalid: "text-warn bg-warn-bg border-warn/35",
  none: "text-none bg-none-bg border-none/30",
};

const VERDICT_WORD: Record<Verdict, string> = {
  pass: "PASS",
  fail: "FAIL",
  invalid: "INVALID",
  none: "N/A",
};

export function VerdictChip({
  verdict,
  label,
}: {
  verdict: Verdict;
  label?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-[11px] font-medium tracking-[0.01em] ${VERDICT_STYLE[verdict]}`}
    >
      <Glyph verdict={verdict} />
      {label ?? VERDICT_WORD[verdict]}
    </span>
  );
}

/* The four decisions are not a pass/fail axis. ESCALATE is the correct outcome
   for an under-specified issue, so it must not be styled as a failure. */
const DECISION_STYLE: Record<string, string> = {
  ACCEPT: "text-pass bg-pass-bg border-pass/40",
  REJECT: "text-fail bg-fail-bg border-fail/40",
  ESCALATE: "text-accent bg-surface-2 border-accent/40",
  "REVIEW REQUIRED": "text-warn bg-warn-bg border-warn/40",
};

export function DecisionBadge({ decision }: { decision: string }) {
  return (
    <span
      className={`inline-block rounded-full border px-3.5 py-1.5 text-[12px] font-semibold tracking-[0.02em] ${
        DECISION_STYLE[decision] ?? DECISION_STYLE["REVIEW REQUIRED"]
      }`}
    >
      {decision}
    </span>
  );
}

export function Card({
  title,
  aside,
  children,
  className = "",
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`card min-w-0 rounded-[var(--radius)] border border-border bg-surface ${className}`}
    >
      {title !== undefined && (
        <header className="flex items-baseline justify-between gap-3 border-b border-border px-5 py-3.5">
          <h2 className="t-section">{title}</h2>
          {aside}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="t-caption">{label}</dt>
      <dd className="font-mono text-[13.5px] text-fg">{children}</dd>
    </div>
  );
}

/** One suite column. The three always render together in a fixed order so the
 *  green-visible / red-gold contrast is the thing the eye lands on. */
export function SuiteColumn({
  label,
  run,
  note,
  emphasis = false,
}: {
  label: string;
  run: TestRun | null;
  note?: string;
  emphasis?: boolean;
}) {
  const verdict: Verdict = run === null ? "none" : run.passed ? "pass" : "fail";
  return (
    <div
      className={`min-w-0 rounded-[var(--radius)] border p-4 ${
        emphasis ? "border-border-strong" : "border-border"
      } bg-surface-2`}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="t-section">{label}</h3>
        <VerdictChip verdict={verdict} />
      </div>
      {run === null ? (
        <p className="font-mono text-xs text-fg-faint">
          {note ?? "did not run"}
        </p>
      ) : (
        <dl className="grid grid-cols-3 gap-3">
          <div>
            <dt className="t-caption">tests</dt>
            <dd className="mt-0.5 text-[19px] font-medium tracking-[-0.01em]">
              {run.total}
            </dd>
          </div>
          <div>
            <dt className="t-caption">failed</dt>
            <dd
              className={`mt-0.5 text-[19px] font-medium tracking-[-0.01em] ${run.failures > 0 ? "text-fail" : "text-fg-faint"}`}
            >
              {run.failures}
            </dd>
          </div>
          <div>
            <dt className="t-caption">errors</dt>
            <dd
              className={`mt-0.5 text-[19px] font-medium tracking-[-0.01em] ${run.errors > 0 ? "text-warn" : "text-fg-faint"}`}
            >
              {run.errors}
            </dd>
          </div>
        </dl>
      )}
      {note && run !== null && (
        <p className="mt-2 text-[11px] text-fg-faint">{note}</p>
      )}
    </div>
  );
}

/** A truncated attempt must be visible at a glance, not buried in patch notes. */
export function StopReasonNote({ reason }: { reason: string | null }) {
  if (reason === null || reason === "finished") return null;
  return (
    <p className="rounded-[var(--radius-sm)] border border-warn/30 bg-warn-bg px-4 py-2.5 text-[13px] leading-relaxed text-warn">
      <strong className="font-semibold">Truncated attempt.</strong> The agent
      stopped with <code className="font-mono">{reason}</code> rather than{" "}
      <code className="font-mono">finished</code>, so the patch and the evidence
      below may be partial.
    </p>
  );
}

export function DegradedNote({ run }: { run: RunResult }) {
  if (!run.degraded) return null;
  return (
    <p className="rounded-[var(--radius-sm)] border border-warn/30 bg-warn-bg px-4 py-2.5 text-[13px] leading-relaxed text-warn">
      <strong className="font-semibold">Degraded run.</strong>{" "}
      {run.degraded_reason ||
        "a role was served by a model other than the pinned one"}
      . Excluded from the headline metric.
    </p>
  );
}

/** Colourised unified diff. Wrapped in its own scroll box - the page never
 *  scrolls sideways because a patch line was long. */
export function Diff({ diff }: { diff: string }) {
  if (!diff.trim())
    return <p className="font-mono text-xs text-fg-faint">empty patch</p>;
  return (
    <pre className="scroll-x max-h-[28rem] overflow-y-auto rounded-[var(--radius-sm)] border border-border bg-surface-2 p-4 font-mono text-[12.5px] leading-[1.6]">
      {diff.split("\n").map((line, i) => {
        const add = line.startsWith("+") && !line.startsWith("+++");
        const del = line.startsWith("-") && !line.startsWith("---");
        const meta = line.startsWith("@@") || line.startsWith("diff ");
        return (
          <div
            key={i}
            className={
              add
                ? "text-[var(--add)]"
                : del
                  ? "text-[var(--del)]"
                  : meta
                    ? "text-fg-faint"
                    : "text-fg-muted"
            }
          >
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}
