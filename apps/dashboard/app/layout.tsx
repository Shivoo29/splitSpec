import type { Metadata } from "next";
import Link from "next/link";
import { loadEntries } from "@/lib/artifacts";
import { VerdictChip } from "@/components/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: "SplitSpec Evidence",
  description: "Read-only viewer over SplitSpec run artifacts",
};

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const entries = await loadEntries();

  return (
    <html lang="en">
      <body className="min-h-dvh">
        <div className="flex min-h-dvh">
          {/* Fixed rail: the run list is the primary navigation and stays put on
              every route, so a reader never loses their place in the sweep. */}
          <nav
            aria-label="Runs"
            className="hidden w-[var(--rail)] shrink-0 flex-col border-r border-border bg-surface lg:flex"
          >
            <div className="border-b border-border px-4 py-3.5">
              <Link href="/" className="font-mono text-sm font-semibold tracking-tight">
                SplitSpec
              </Link>
              <p className="mt-0.5 text-[11px] text-fg-faint">evidence viewer</p>
            </div>

            <div className="flex flex-col gap-1 overflow-y-auto p-2">
              <Link
                href="/compare"
                className="rounded-[var(--radius)] px-2.5 py-1.5 text-[13px] text-fg-muted transition-colors duration-150 hover:bg-surface-2 hover:text-fg"
              >
                Comparison
              </Link>

              <p className="mt-2 px-2.5 pb-1 text-[11px] tracking-wide text-fg-faint uppercase">
                Runs ({entries.length})
              </p>

              {entries.length === 0 && (
                <p className="px-2.5 py-1 text-[12px] text-fg-faint">
                  No runs in artifacts/ yet.
                </p>
              )}

              {entries.map((entry) => (
                <Link
                  key={entry.id}
                  href={`/run/${entry.id}`}
                  className="flex items-center justify-between gap-2 rounded-[var(--radius)] px-2.5 py-1.5 transition-colors duration-150 hover:bg-surface-2"
                >
                  <span className="truncate font-mono text-[12px]">{entry.id}</span>
                  {entry.kind === "failed" ? (
                    <VerdictChip verdict="invalid" label="ERR" />
                  ) : (
                    <VerdictChip
                      verdict={entry.run.gold?.passed ? "pass" : "fail"}
                      label={entry.run.gold ? (entry.run.gold.passed ? "GOLD" : "GOLD") : "N/A"}
                    />
                  )}
                </Link>
              ))}
            </div>
          </nav>

          <main className="min-w-0 flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
