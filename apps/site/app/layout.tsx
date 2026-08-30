import type { Metadata } from "next";
import "./globals.css";

const REPO = "https://github.com/Shivoo29/splitSpec";

export const metadata: Metadata = {
  title: "SplitSpec — independent verification for AI-generated bug fixes",
  description:
    "The agent that writes the fix never sees the test that grades the fix. A measured study of whether an independent verifier can clear AI-authored patches without a human reading every one.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh">
        {/* A single quiet bar. The page has one job and one link out; a nav with
            five items would imply a product that does not exist yet. */}
        <header className="sticky top-0 z-10 border-b border-border bg-bg/80 backdrop-blur-xl">
          <div className="mx-auto flex max-w-[980px] items-center justify-between px-6 py-3.5">
            <a href="#top" className="text-[15px] font-semibold tracking-[-0.017em]">
              SplitSpec
            </a>
            <a
              href={REPO}
              className="rounded-full border border-border px-3.5 py-1.5 text-[13px] font-medium text-fg-muted hover:border-border-strong hover:text-fg"
            >
              View source
            </a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="mt-24 border-t border-border">
          <div className="mx-auto max-w-[980px] px-6 py-10">
            <p className="t-caption max-w-[62ch]">
              A research prototype, not a product. Results hold for the documented models,
              prompts, cases, and environment, and nothing wider. SplitSpec merges nothing and
              approves nothing on its own; every decision it produces is advisory evidence for a
              human reviewer.
            </p>
            <p className="t-caption mt-4">
              <a className="text-accent hover:underline" href={REPO}>
                Source and full results
              </a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
