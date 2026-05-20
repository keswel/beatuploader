import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Disc3 } from "lucide-react";

interface Props {
  title: string;
  updated: string;
  children: ReactNode;
}

export function LegalLayout({ title, updated, children }: Props) {
  return (
    <div className="min-h-screen w-screen flex justify-center px-6 py-16">
      <div className="w-full max-w-2xl">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-zinc-500 hover:text-zinc-300 transition-colors text-xs mb-8"
        >
          <div className="flex h-6 w-6 items-center justify-center rounded bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950">
            <Disc3 className="h-3 w-3" />
          </div>
          Beatuploader
        </Link>

        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <div className="text-xs text-zinc-500 mt-1 mb-10">
          Last updated {updated}
        </div>

        {/* Minimal typography styling, scoped to children. No prose plugin needed. */}
        <div
          className={[
            "text-sm text-zinc-300 leading-relaxed",
            "[&>h2]:text-lg [&>h2]:font-semibold [&>h2]:tracking-tight",
            "[&>h2]:text-zinc-100 [&>h2]:mt-10 [&>h2]:mb-3",
            "[&>p]:my-3",
            "[&>ul]:my-3 [&>ul]:list-disc [&>ul]:pl-5 [&>ul]:space-y-1.5",
            "[&_a]:text-zinc-100 [&_a]:underline [&_a]:underline-offset-2",
            "hover:[&_a]:text-white",
            "[&_strong]:text-zinc-100 [&_strong]:font-semibold",
            "[&_code]:text-zinc-100 [&_code]:bg-zinc-900",
            "[&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-[12px]",
          ].join(" ")}
        >
          {children}
        </div>

        <div className="mt-16 pt-6 border-t border-zinc-900 flex items-center justify-between text-xs text-zinc-500">
          <Link to="/privacy" className="hover:text-zinc-300 transition-colors">
            Privacy
          </Link>
          <Link to="/terms" className="hover:text-zinc-300 transition-colors">
            Terms
          </Link>
          <a
            href="mailto:hello@beatuploader.com"
            className="hover:text-zinc-300 transition-colors"
          >
            Contact
          </a>
        </div>
      </div>
    </div>
  );
}
