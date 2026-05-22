import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "motion/react";
import {
  Disc3,
  LayoutDashboard,
  Library,
  LogOut,
  Menu,
  Plug,
  Settings,
  UploadCloud,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

/**
 * Hamburger trigger + slide-in sheet of the same nav items the desktop
 * sidebar shows. Mobile-only — sidebar takes over from md: up.
 *
 * Auto-closes on route change so tapping a link doesn't leave the sheet
 * hanging on top of the new page.
 */
const navItems = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/upload", label: "Upload", icon: UploadCloud },
  { to: "/platforms", label: "Platforms", icon: Plug },
  { to: "/library", label: "Library", icon: Library },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const { user, logout } = useAuth();
  const initials = user?.handle.slice(0, 2).toUpperCase() ?? "??";

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="md:hidden h-9 w-9 rounded-md text-zinc-300 hover:bg-zinc-900 hover:text-zinc-50 transition-colors flex items-center justify-center"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>
      </Dialog.Trigger>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild>
              <motion.div
                className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              />
            </Dialog.Overlay>
            <Dialog.Content asChild>
              <motion.aside
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={{ duration: 0.35, ease: [0.32, 0.72, 0, 1] }}
                className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[80vw] flex-col border-r border-zinc-800/60 bg-zinc-950 md:hidden"
              >
                <Dialog.Title className="sr-only">Navigation</Dialog.Title>
                <Dialog.Description className="sr-only">
                  Beatuploader navigation menu
                </Dialog.Description>

                <div className="flex h-14 items-center justify-between px-5 border-b border-zinc-800/60">
                  <Link to="/dashboard" className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950">
                      <Disc3 className="h-4 w-4" />
                    </div>
                    <span className="text-sm font-semibold tracking-tight">
                      Beatuploader
                    </span>
                  </Link>
                  <Dialog.Close asChild>
                    <button
                      type="button"
                      className="h-8 w-8 rounded-md text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200 transition-colors flex items-center justify-center"
                      aria-label="Close menu"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </Dialog.Close>
                </div>

                <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
                  <div className="px-2 pb-2 text-[10px] font-medium uppercase tracking-widest text-zinc-600">
                    Workspace
                  </div>
                  {navItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        end={item.end}
                        className={({ isActive }) =>
                          cn(
                            "flex items-center gap-3 rounded-md px-2.5 py-2.5 text-sm font-medium transition-colors",
                            isActive
                              ? "bg-zinc-900 text-zinc-50 border border-zinc-800/80"
                              : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900/50",
                          )
                        }
                      >
                        <Icon className="h-4 w-4 text-zinc-500" />
                        {item.label}
                      </NavLink>
                    );
                  })}
                </nav>

                <div className="border-t border-zinc-800/60 p-3 space-y-1">
                  <NavLink
                    to="/settings"
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 rounded-md px-2.5 py-2.5 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-zinc-900 text-zinc-50 border border-zinc-800/80"
                          : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900/50",
                      )
                    }
                  >
                    <Settings className="h-4 w-4 text-zinc-500" />
                    Settings
                  </NavLink>
                  <button
                    type="button"
                    onClick={logout}
                    className="w-full flex items-center gap-3 rounded-md px-2.5 py-2.5 text-sm font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900/50 transition-colors"
                  >
                    <LogOut className="h-4 w-4 text-zinc-500" />
                    Sign out
                  </button>

                  <div className="mt-3 rounded-lg border border-zinc-800/60 bg-zinc-900/40 p-3">
                    <div className="flex items-center gap-2.5">
                      <div className="h-8 w-8 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-900 ring-1 ring-zinc-700/50 flex items-center justify-center text-xs font-semibold">
                        {initials}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">
                          {user?.handle ?? "—"}
                        </div>
                        <div className="text-[10px] text-zinc-500 truncate capitalize">
                          {user?.plan ?? "free"} plan
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.aside>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
