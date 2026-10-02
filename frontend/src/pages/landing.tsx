import { Link } from "react-router-dom";

// Public holding page for beatuploader.app until the first desktop release.
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
          <span className="text-sm font-semibold tracking-tight">beatuploader</span>
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

          <p className="mt-14 flex items-center gap-2.5 text-sm text-zinc-300">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden />
            Coming soon
          </p>
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
