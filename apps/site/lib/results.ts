import { promises as fs } from "node:fs";
import path from "node:path";

/**
 * Reads the committed run artifacts at BUILD time, so every figure on the page is
 * the measured one and the output is still a static file with no server.
 *
 * Nothing here is hand-written. If a number on the site is wrong, the run that
 * produced it is wrong - which is the property a page making empirical claims
 * needs to have.
 */

const ARTIFACTS = path.resolve(process.cwd(), "../../artifacts");

interface Suite {
  passed: boolean;
  total: number;
  failures: number;
}

interface Run {
  case_id: string;
  mode: "baseline" | "splitspec";
  decision: string;
  runtime_sec: number;
  visible: Suite | null;
  verifier: Suite | null;
  gold: Suite | null;
  validity: { passed: boolean } | null;
  mutation: { killed: boolean; scored?: boolean }[];
}

export interface Results {
  baselineRuns: number;
  splitspecRuns: number;
  incomplete: number;
  /** Correct patches (gold passed) that SplitSpec cleared without a human. */
  cleared: number;
  correct: number;
  /** Broken patches (gold failed) that were cleared anyway - the honest miss. */
  brokenCleared: number;
  broken: number;
  reviewsBaseline: number;
  reviewsSplitspec: number;
  validityValid: number;
  validityTotal: number;
  mutantsKilled: number;
  mutantsTotal: number;
  medianBaseline: number;
  medianSplitspec: number;
  rows: {
    caseId: string;
    baseline: string | null;
    splitspec: string | null;
    goldBaseline: boolean | null;
    goldSplitspec: boolean | null;
  }[];
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

export async function loadResults(): Promise<Results> {
  const runs: Run[] = [];
  let incomplete = 0;

  let dirs: string[] = [];
  try {
    dirs = (await fs.readdir(ARTIFACTS, { withFileTypes: true }))
      .filter((d) => d.isDirectory() && d.name.startsWith("issue-"))
      .map((d) => d.name)
      .sort();
  } catch {
    dirs = [];
  }

  for (const dir of dirs) {
    let raw: string;
    try {
      raw = await fs.readFile(path.join(ARTIFACTS, dir, "result.json"), "utf8");
    } catch {
      continue;
    }
    const data = JSON.parse(raw);
    // A pair that raised mid-sweep is not a run that scored zero; it is counted
    // separately and never enters a denominator.
    if (data?.ok === false) {
      incomplete += 1;
      continue;
    }
    runs.push(data as Run);
  }

  const baseline = runs.filter((r) => r.mode === "baseline");
  const splitspec = runs.filter((r) => r.mode === "splitspec");

  const correctRuns = splitspec.filter((r) => r.gold?.passed);
  const brokenRuns = splitspec.filter((r) => r.gold && !r.gold.passed);
  const gated = splitspec.filter((r) => r.validity !== null);
  const mutants = splitspec.flatMap((r) =>
    r.mutation.filter((m) => m.scored !== false),
  );

  const caseIds = [...new Set(runs.map((r) => r.case_id))].sort();
  const rows = caseIds.map((caseId) => {
    const b = baseline.find((r) => r.case_id === caseId);
    const s = splitspec.find((r) => r.case_id === caseId);
    return {
      caseId,
      baseline: b?.decision ?? null,
      splitspec: s?.decision ?? null,
      goldBaseline: b?.gold ? b.gold.passed : null,
      goldSplitspec: s?.gold ? s.gold.passed : null,
    };
  });

  return {
    baselineRuns: baseline.length,
    splitspecRuns: splitspec.length,
    incomplete,
    cleared: correctRuns.filter((r) => r.decision === "ACCEPT").length,
    correct: correctRuns.length,
    brokenCleared: brokenRuns.filter((r) => r.decision === "ACCEPT").length,
    broken: brokenRuns.length,
    reviewsBaseline: baseline.filter((r) => r.decision !== "ACCEPT").length,
    reviewsSplitspec: splitspec.filter((r) => r.decision !== "ACCEPT").length,
    validityValid: gated.filter((r) => r.validity!.passed).length,
    validityTotal: gated.length,
    mutantsKilled: mutants.filter((m) => m.killed).length,
    mutantsTotal: mutants.length,
    medianBaseline: median(baseline.map((r) => r.runtime_sec)),
    medianSplitspec: median(splitspec.map((r) => r.runtime_sec)),
    rows,
  };
}
