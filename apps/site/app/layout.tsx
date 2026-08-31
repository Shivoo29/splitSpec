import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

const REPO = "https://github.com/Shivoo29/splitSpec";

export const metadata: Metadata = {
  title: "SplitSpec — independent verification for AI-generated bug fixes",
  description:
    "The agent that writes the fix never sees the test that grades the fix. A measured study of whether an independent verifier can clear AI-authored patches without a human reading every one.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/runs", label: "Runs" },
  { href: "/compare", label: "Compare" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-dvh">
        {/* One bar across every route. The evidence pages and the story page are
            the same site, so they share navigation rather than living apart. */}
        <header className="sticky top-0 z-20 border-b border-border bg-bg/75 backdrop-blur-xl">
          <div className="mx-auto flex max-w-[1120px] items-center gap-6 px-6 py-3.5">
            <Link href="/" className="flex items-center gap-2.5">
              <span
                aria-hidden
                className="inline-block h-[18px] w-[18px] rounded-[6px] bg-brand"
                style={{
                  background:
                    "linear-gradient(135deg, var(--brand) 40%, var(--verifier))",
                }}
              />
              <span className="text-[15px] font-semibold tracking-[-0.017em]">
                SplitSpec
              </span>
            </Link>

            <nav className="flex items-center gap-1 text-[14px]">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-full px-3 py-1.5 text-fg-muted transition-colors hover:bg-surface-2 hover:text-fg"
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            <a
              href={REPO}
              className="ml-auto rounded-full border border-border px-3.5 py-1.5 text-[13px] font-medium text-fg-muted transition-colors hover:border-border-strong hover:text-fg"
            >
              Source
            </a>
          </div>
        </header>

        <main>{children}</main>

        <footer className="mt-24 border-t border-border">
          <div className="mx-auto max-w-[1120px] px-6 py-10">
            <p className="t-caption max-w-[64ch]">
              A research prototype, not a product. Results hold for the
              documented models, prompts, cases, and environment, and nothing
              wider. SplitSpec merges nothing and approves nothing on its own;
              every decision it produces is advisory evidence for a human
              reviewer.
            </p>
            <p className="t-caption mt-4">
              <a className="text-brand hover:underline" href={REPO}>
                Source and full results
              </a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
