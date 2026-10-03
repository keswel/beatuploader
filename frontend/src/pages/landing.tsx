import { Link } from "react-router-dom";
import { Logo } from "@/components/logo";
import { DONATE_URL, DOWNLOAD_URL } from "@/lib/target";

// Public page for beatuploader.app: what it does, download, donate.
// Deliberately plain: type and spacing, no glows, badges, or icon cards.

const WHAT_IT_DOES = [
  "Drop in the tagged MP3, WAV, stems and cover art.",
  "It picks licenses based on the files you give it.",
  "One click uploads to BeatStars and YouTube.",
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto flex min-h-screen max-w-2xl flex-col px-6">
        <header className="pt-8 sm:pt-10">
          <span className="flex items-center gap-2.5 text-sm font-semibold tracking-tight">
            <Logo className="h-6" />
            beatuploader
          </span>
        </header>

        <main className="flex-1 pt-24 pb-20 sm:pt-36">
          <h1 className="text-4xl font-semibold leading-[1.1] tracking-[-0.03em] sm:text-5xl">
            Upload a beat once.
            <br />
            <span className="text-zinc-500">It goes everywhere.</span>
          </h1>

          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-zinc-400">
            A free Windows app for producers. It runs on your own computer, so
            your BeatStars and YouTube logins never leave it.
          </p>

          <ol className="mt-12 space-y-3 border-l border-zinc-800 pl-5 text-[15px] text-zinc-300">
            {WHAT_IT_DOES.map((line, i) => (
              <li key={line} className="flex gap-4">
                <span className="w-4 shrink-0 font-mono text-xs leading-6 text-zinc-600">
                  {i + 1}
                </span>
                {line}
              </li>
            ))}
          </ol>

          <div className="mt-14">
            <a
              href={DOWNLOAD_URL}
              className="inline-flex items-center rounded-md bg-zinc-100 px-4 py-2.5 text-sm font-medium text-zinc-950 transition-colors hover:bg-white"
            >
              Download for Windows
            </a>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-zinc-500">
              Windows 10 or 11. The installer isn&apos;t code-signed yet, so
              Windows may show &ldquo;Windows protected your PC&rdquo;. Click{" "}
              <span className="text-zinc-300">More info</span>, then{" "}
              <span className="text-zinc-300">Run anyway</span>. The app updates
              itself after that.
            </p>
          </div>

          {DONATE_URL && (
            <p className="mt-10 text-sm text-zinc-400">
              Beatuploader is free. If it saves you time,{" "}
              <a
                href={DONATE_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-100 underline decoration-zinc-600 underline-offset-4 transition-colors hover:decoration-zinc-300"
              >
                you can donate here
              </a>
              .
            </p>
          )}
          <p className="mt-2 text-sm text-zinc-600">
            FL Studio export detection is next on the list.
          </p>
        </main>

        <footer className="flex flex-wrap gap-x-5 gap-y-2 border-t border-zinc-900 py-6 text-xs text-zinc-600">
          <span>© {new Date().getFullYear()} Beatuploader</span>
          <Link to="/privacy" className="transition-colors hover:text-zinc-300">
            Privacy
          </Link>
          <Link to="/terms" className="transition-colors hover:text-zinc-300">
            Terms
          </Link>
        </footer>
      </div>
    </div>
  );
}
