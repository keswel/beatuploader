import { NavLink, useLocation } from "react-router-dom";
import { motion } from "motion/react";
import {
  LayoutDashboard,
  UploadCloud,
  Plug,
  Library,
  Settings,
  Disc3,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const navItems = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/upload", label: "Upload", icon: UploadCloud },
  { to: "/platforms", label: "Platforms", icon: Plug },
  { to: "/library", label: "Library", icon: Library },
];

export function Sidebar() {
  const location = useLocation();
  const { user, logout } = useAuth();

  const initials = user?.handle.slice(0, 2).toUpperCase() ?? "??";

  return (
    <aside className="hidden md:flex w-60 flex-col border-r border-zinc-800/60 bg-zinc-950/40 backdrop-blur-sm">
      <div className="flex h-14 items-center gap-2 px-5 border-b border-zinc-800/60">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
          className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950 shadow-[0_0_20px_-4px_rgba(255,255,255,0.3)]"
        >
          <Disc3 className="h-4 w-4" />
        </motion.div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold tracking-tight">Beatuploader</span>
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Studio</span>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <div className="px-2 pb-2 text-[10px] font-medium uppercase tracking-widest text-zinc-600">
          Workspace
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = item.end
            ? location.pathname === item.to
            : location.pathname.startsWith(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className="relative group flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium"
            >
              {isActive && (
                <motion.div
                  layoutId="sidebar-pill"
                  className="absolute inset-0 rounded-md bg-zinc-900 shadow-[0_1px_0_0_rgba(255,255,255,0.05)_inset] border border-zinc-800/80"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                />
              )}
              <Icon
                className={cn(
                  "relative h-4 w-4 transition-colors duration-200",
                  isActive
                    ? "text-zinc-100"
                    : "text-zinc-500 group-hover:text-zinc-300",
                )}
              />
              <span
                className={cn(
                  "relative transition-colors duration-200",
                  isActive ? "text-zinc-50" : "text-zinc-400 group-hover:text-zinc-100",
                )}
              >
                {item.label}
              </span>
            </NavLink>
          );
        })}
      </nav>

      <div className="px-3 pb-3 space-y-0.5">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              "w-full flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors duration-200",
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
          className="w-full flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900/50 transition-colors duration-200"
        >
          <LogOut className="h-4 w-4 text-zinc-500" />
          Sign out
        </button>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="mt-3 rounded-lg border border-zinc-800/60 bg-zinc-900/40 p-3"
        >
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-900 ring-1 ring-zinc-700/50 flex items-center justify-center text-xs font-semibold">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">{user?.handle ?? "—"}</div>
              <div className="text-[10px] text-zinc-500 truncate capitalize">
                {user?.plan ?? "free"} plan
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </aside>
  );
}
