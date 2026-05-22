import { Link } from "react-router-dom";
import { Bell, Command, Disc3, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MobileNav } from "./mobile-nav";
import { useAuth } from "@/lib/auth";

export function Topbar() {
  const { user } = useAuth();
  const initials = user?.handle.slice(0, 2).toUpperCase() ?? "??";

  return (
    <header className="sticky top-0 z-20 h-14 border-b border-zinc-800/60 glass">
      <div className="flex h-full items-center gap-2 sm:gap-3 px-4 sm:px-6">
        {/* Mobile-only: hamburger + wordmark. The desktop sidebar carries the
            brand on >= md, so we render the wordmark only here on small. */}
        <MobileNav />
        <Link
          to="/dashboard"
          className="md:hidden flex items-center gap-2"
          aria-label="Beatuploader"
        >
          <div className="flex h-6 w-6 items-center justify-center rounded bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950">
            <Disc3 className="h-3 w-3" />
          </div>
          <span className="text-sm font-semibold tracking-tight">
            Beatuploader
          </span>
        </Link>

        {/* Search is desktop-only — it's mostly aspirational right now and just
            crowds the mobile header. */}
        <div className="relative flex-1 max-w-md hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
          <input
            type="text"
            placeholder="Search beats, uploads, platforms..."
            className="w-full h-9 rounded-md border border-zinc-800/80 bg-zinc-900/30 pl-9 pr-16 text-sm placeholder:text-zinc-500 focus:outline-none focus:border-zinc-700 focus:bg-zinc-900/60 transition-all duration-200"
          />
          <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 hidden md:inline-flex items-center gap-1 rounded border border-zinc-800 bg-zinc-900/70 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500">
            <Command className="h-2.5 w-2.5" />K
          </kbd>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" size="icon" className="relative">
            <Bell className="h-4 w-4" />
            <span className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-zinc-300 ring-2 ring-zinc-950 pulse-ring" />
          </Button>
          <div className="h-6 w-px bg-zinc-800" />
          <div className="flex items-center gap-2.5 pl-1 pr-2">
            <div className="h-7 w-7 rounded-full bg-gradient-to-br from-zinc-600 to-zinc-900 ring-1 ring-zinc-700/50 flex items-center justify-center text-[10px] font-semibold text-zinc-200">
              {initials}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
