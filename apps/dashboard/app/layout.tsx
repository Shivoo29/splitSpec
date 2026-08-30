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

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
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
            <div className="border-b border-border px-5 py-5">
              <Link
                href="/"
                className="text-[17px] font-semibold tracking-[-0.017em]"
              >
                SplitSpec
              </Link>
              <p className="mt-0.5 text-[12px] text-fg-faint">
                Evidence viewer
              </p>
            </div>

            <div className="flex flex-col gap-0.5 overflow-y-auto p-3">
              <Link
                href="/compare"
                className="rounded-[var(--radius-sm)] px-3 py-2 text-[14px] text-fg-muted hover:bg-surface-2 hover:text-fg"
              >
                Comparison
              </Link>

              <p className="t-section mt-5 px-3 pb-2">
                Runs ({entries.length})
              </p>

              {entries.length === 0 && (
                <p className="px-3 py-2 text-[13px] text-fg-faint">
                  No runs in artifacts/ yet.
                </p>
              )}

              {entries.map((entry) => (
                <Link
                  key={entry.id}
                  href={`/run/${entry.id}`}
                  className="flex items-center justify-between gap-2 rounded-[var(--radius-sm)] px-3 py-2 hover:bg-surface-2"
                >
                  <span className="truncate font-mono text-[12.5px]">
                    {entry.id}
                  </span>
                  {entry.kind === "failed" ? (
                    <VerdictChip verdict="invalid" label="ERR" />
                  ) : (
                    // The gold suite is the ground truth, so it is what the rail
                    // summarises. Pass and fail differ by glyph as well as colour.
                    <VerdictChip
                      verdict={
                        entry.run.gold
                          ? entry.run.gold.passed
                            ? "pass"
                            : "fail"
                          : "none"
                      }
                      label="GOLD"
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
