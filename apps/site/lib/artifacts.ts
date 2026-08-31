import { promises as fs } from "node:fs";
import path from "node:path";

/**
 * Reads the run artifacts off disk. Server-only: no route in this app ever hands
 * a filesystem path to the client.
 *
 * The types mirror splitspec/schemas.py. Where a field's meaning is easy to get
 * backwards, the comment says what the wrong reading would look like on screen.
 */

// Read at BUILD time, not request time: the whole site static-exports, so it
// deploys to any host with no server and the numbers are frozen with the commit
// that produced them.
export const ARTIFACTS_DIR = path.resolve(process.cwd(), "../../artifacts");

export type Verdict = "pass" | "fail" | "invalid" | "none";

export interface TestRun {
  label: string;
  command: string;
  passed: boolean;
  total: number;
  failures: number;
  errors: number;
  duration_sec: number;
  stdout_tail: string;
  junit_xml_path: string | null;
}

export interface MutationResult {
  mutant_id: string;
  description: string;
  killed: boolean;
  detail: string;
  /** False for a mutant no in-process test can kill. Excluded from the score
   *  denominator upstream; showing it as a miss would contradict the artifact. */
  scored: boolean;
}

export interface RunResult {
  case_id: string;
  mode: "baseline" | "splitspec";
  models: { role: string; base_url: string; model: string }[];
  degraded: boolean;
  degraded_reason: string;
  contract: {
    summary: string;
    invariants: string[];
    ambiguities: string[];
    out_of_scope: string[];
    confidence: "low" | "medium" | "high";
  } | null;
  patch: {
    diff: string;
    files_changed: string[];
    lines_added: number;
    lines_removed: number;
    /** An EXISTING test was modified. Adding a test is permitted and is not this. */
    touched_tests: boolean;
    notes: string;
  } | null;
  verifier_test: {
    filename: string;
    invariant: string;
    assumptions: string[];
  } | null;
  validity: {
    compiles: boolean | null;
    runs: boolean | null;
    fails_on_original_bug: boolean | null;
    passed: boolean;
    reason: string;
  } | null;
  visible: TestRun | null;
  verifier: TestRun | null;
  gold: TestRun | null;
  mutation: MutationResult[];
  decision: "ACCEPT" | "REVIEW REQUIRED" | "REJECT" | "ESCALATE";
  runtime_sec: number;
  cost_usd: number;
  artifact_dir: string;
}

/** A pair that raised mid-sweep. NOT a run with zero passing tests - those are
 *  opposite findings and must never render the same way. */
export interface FailedRun {
  ok: false;
  case_id: string;
  mode: "baseline" | "splitspec";
  error: string;
}

export type Entry =
  | { id: string; kind: "run"; run: RunResult; packet: string | null }
  | { id: string; kind: "failed"; run: FailedRun };

function isFailure(data: unknown): data is FailedRun {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as { ok?: unknown }).ok === false
  );
}

export async function loadEntries(): Promise<Entry[]> {
  let dirs: string[];
  try {
    dirs = (await fs.readdir(ARTIFACTS_DIR, { withFileTypes: true }))
      .filter((d) => d.isDirectory())
      .map((d) => d.name)
      .sort();
  } catch {
    return [];
  }

  const entries: Entry[] = [];
  for (const id of dirs) {
    const file = path.join(ARTIFACTS_DIR, id, "result.json");
    let raw: string;
    try {
      raw = await fs.readFile(file, "utf8");
    } catch {
      continue; // a directory without a result.json is not a run
    }
    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch {
      continue;
    }
    if (isFailure(data)) {
      entries.push({ id, kind: "failed", run: data });
      continue;
    }
    const packet = await fs
      .readFile(path.join(ARTIFACTS_DIR, id, "review_packet.md"), "utf8")
      .catch(() => null);
    entries.push({ id, kind: "run", run: data as RunResult, packet });
  }
  return entries;
}

export async function loadEntry(id: string): Promise<Entry | null> {
  const all = await loadEntries();
  return all.find((e) => e.id === id) ?? null;
}

export function verdictOf(run: TestRun | null): Verdict {
  if (run === null) return "none";
  return run.passed ? "pass" : "fail";
}

/** The fixer records its stop reason in patch.notes as `stop_reason=...`.
 *  A patch from an agent that stopped on budget is a truncated attempt; a reader
 *  who cannot see that will read "the model failed" where "the model was cut
 *  off" is the truth. */
export function stopReason(run: RunResult): string | null {
  const notes = run.patch?.notes;
  if (!notes) return null;
  if (!notes.startsWith("stop_reason=")) return notes.trim() || null;
  const rest = notes.slice("stop_reason=".length);
  const end = rest.indexOf(";");
  return (end === -1 ? rest : rest.slice(0, end)).trim();
}

/** Score over SCORED mutants only, matching mutation_results.json. Counting the
 *  unkillable ones here would put two different scores for one run on screen. */
export function mutationScore(mutation: MutationResult[]): {
  killed: number;
  denominator: number;
  excluded: string[];
} {
  const scored = mutation.filter((m) => m.scored);
  return {
    killed: scored.filter((m) => m.killed).length,
    denominator: scored.length,
    excluded: mutation.filter((m) => !m.scored).map((m) => m.mutant_id),
  };
}

/** Cost is 0.0 in every run because the agents drop model_use before it reaches
 *  RunResult. Unmeasured is not zero, so it never renders as "$0.00". */
export function costLabel(run: RunResult): string {
  return run.cost_usd > 0 ? `$${run.cost_usd.toFixed(4)}` : "not measured";
}

export function caseIdOf(entry: Entry): string {
  return entry.run.case_id;
}

/**
 * The decision rule, mirroring splitspec/reporting.py `decide()`.
 *
 * Recomputed here rather than rendering `result.decision`, because a stored
 * decision can be stale: every run written before Module 11 existed carries the
 * default "REVIEW REQUIRED". Showing that verbatim puts a REVIEW REQUIRED badge
 * directly beside a red visible-FAIL column, which is the one thing a reader has
 * to be able to trust at a glance. If the rule in reporting.py changes, change it
 * here too — the two must not drift.
 */
export function decide(run: RunResult): RunResult["decision"] {
  if (run.contract?.confidence === "low") return "ESCALATE";
  if (run.visible !== null && !run.visible.passed) return "REJECT";
  if (run.patch?.touched_tests) return "REJECT";
  const validVerifier =
    run.validity !== null &&
    run.validity.passed &&
    run.verifier !== null &&
    run.verifier.passed;
  if (run.visible !== null && run.visible.passed && validVerifier)
    return "ACCEPT";
  return "REVIEW REQUIRED";
}
