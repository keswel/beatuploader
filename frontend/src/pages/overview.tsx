import {
  UploadCloud,
  Music2,
  TrendingUp,
  Headphones,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { motion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { Stagger, StaggerItem, FadeUp } from "@/components/motion";
import { api } from "@/lib/api";
import type { UploadStatus } from "@/lib/types";

const statusMeta: Record<
  UploadStatus,
  { icon: React.ElementType; color: string; label: string }
> = {
  done: { icon: CheckCircle2, color: "text-emerald-400", label: "Live" },
  uploading: { icon: Clock, color: "text-amber-400", label: "Uploading" },
  queued: { icon: Clock, color: "text-zinc-400", label: "Queued" },
  failed: { icon: AlertCircle, color: "text-red-400", label: "Failed" },
};

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86_400 * 7) return `${Math.floor(seconds / 86_400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function OverviewPage() {
  const { data: uploads = [], isLoading: uploadsLoading } = useQuery({
    queryKey: ["uploads"],
    queryFn: api.uploads.list,
  });
  const { data: beats = [], isLoading: beatsLoading } = useQuery({
    queryKey: ["library", ""],
    queryFn: () => api.library.list({ limit: 50 }),
  });
  const { data: platforms = [], isLoading: platformsLoading } = useQuery({
    queryKey: ["platforms"],
    queryFn: api.platforms.list,
  });

  const isLoading = uploadsLoading || beatsLoading || platformsLoading;

  const connectedCount = platforms.filter((p) => p.status === "connected").length;
  const pendingPlatforms = platforms.filter((p) => p.status !== "connected").length;
  const totalPlays = beats.reduce((sum, b) => sum + b.plays, 0);
  const uploadsThisWeek = uploads.filter(
    (u) => Date.now() - new Date(u.created_at).getTime() < 7 * 86_400_000,
  ).length;
  const drafts = beats.filter((b) => !b.released_at).length;
  const recent = uploads.slice(0, 5);

  const stats = [
    {
      label: "Total uploads",
      value: uploads.length.toLocaleString(),
      change: uploadsThisWeek > 0 ? `+${uploadsThisWeek} this week` : "—",
      trend: uploadsThisWeek > 0 ? "up" : "neutral",
      icon: UploadCloud,
    },
    {
      label: "Beats in library",
      value: beats.length.toLocaleString(),
      change: drafts > 0 ? `${drafts} drafts` : "All released",
      trend: "neutral",
      icon: Music2,
    },
    {
      label: "Total plays",
      value: totalPlays >= 1000 ? `${(totalPlays / 1000).toFixed(1)}K` : totalPlays.toString(),
      change: totalPlays > 0 ? "Across all platforms" : "No plays yet",
      trend: "neutral",
      icon: Headphones,
    },
    {
      label: "Connected platforms",
      value: `${connectedCount} / ${platforms.length}`,
      change: pendingPlatforms > 0 ? `${pendingPlatforms} to set up` : "Fully connected",
      trend: "neutral",
      icon: TrendingUp,
    },
  ];

  return (
    <>
      <PageHeader
        title="Overview"
        description="Your release pipeline at a glance."
        actions={
          <>
            <Button variant="outline" size="sm">
              Export report
            </Button>
            <Button asChild size="sm">
              <Link to="/upload">
                <UploadCloud className="h-4 w-4" />
                New upload
              </Link>
            </Button>
          </>
        }
      />

      <Stagger className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 mb-8">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <StaggerItem key={stat.label}>
              <Card interactive className="relative overflow-hidden">
                <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-zinc-700/50 to-transparent" />
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                      {stat.label}
                    </div>
                    <Icon className="h-4 w-4 text-zinc-600" />
                  </div>
                  <div className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">
                    {isLoading ? (
                      <span className="text-zinc-700">—</span>
                    ) : (
                      stat.value
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-1 text-xs">
                    {stat.trend === "up" && (
                      <ArrowUpRight className="h-3 w-3 text-emerald-400" />
                    )}
                    <span
                      className={
                        stat.trend === "up" ? "text-emerald-400" : "text-zinc-500"
                      }
                    >
                      {stat.change}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </StaggerItem>
          );
        })}
      </Stagger>

      <FadeUp delay={0.15} className="grid gap-4 grid-cols-1 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Recent activity</CardTitle>
              <CardDescription>Latest uploads across all platforms</CardDescription>
            </div>
            <Button asChild variant="ghost" size="sm" className="text-zinc-400">
              <Link to="/library">View all</Link>
            </Button>
          </CardHeader>
          <CardContent className="px-0 pb-0">
            {uploadsLoading && (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
              </div>
            )}

            {!uploadsLoading && recent.length === 0 && (
              <div className="px-6 py-12 text-center">
                <UploadCloud className="h-8 w-8 text-zinc-700 mx-auto mb-3" />
                <div className="text-sm font-medium text-zinc-300">
                  No uploads yet
                </div>
                <div className="mt-1 text-xs text-zinc-500">
                  Push your first beat to get started.
                </div>
                <Button asChild size="sm" className="mt-4">
                  <Link to="/upload">Upload a beat</Link>
                </Button>
              </div>
            )}

            <div className="divide-y divide-zinc-800/60">
              {recent.map((item, i) => {
                const meta = statusMeta[item.status];
                const StatusIcon = meta.icon;
                const targetCount = Object.keys(item.targets).length;
                const targetSummary = Object.keys(item.targets)
                  .slice(0, 3)
                  .join(" · ");
                return (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      delay: 0.2 + i * 0.05,
                      duration: 0.4,
                      ease: [0.22, 1, 0.36, 1],
                    }}
                    className="flex items-center gap-4 px-6 py-3.5 hover:bg-zinc-900/30 transition-colors duration-200"
                  >
                    <div className="h-9 w-9 rounded-md bg-gradient-to-br from-zinc-800 to-zinc-900 ring-1 ring-zinc-800 flex items-center justify-center shrink-0">
                      <Music2 className="h-4 w-4 text-zinc-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{item.filename}</div>
                      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-zinc-500">
                        {targetSummary}
                        {targetCount > 3 && <span>+{targetCount - 3}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="hidden sm:flex items-center gap-1.5">
                        <StatusIcon className={`h-3.5 w-3.5 ${meta.color}`} />
                        <span className="text-xs text-zinc-400">{meta.label}</span>
                      </div>
                      <div className="text-xs text-zinc-500 tabular-nums shrink-0 w-20 text-right">
                        {timeAgo(item.created_at)}
                      </div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick actions</CardTitle>
            <CardDescription>Jump straight back into work</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <button className="w-full text-left p-3 rounded-lg border border-zinc-800/60 bg-zinc-900/30 hover:bg-zinc-900/60 transition-colors group">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">Watch FL Studio folder</div>
                  <div className="text-xs text-zinc-500 mt-0.5">
                    Auto-detect new exports
                  </div>
                </div>
                <Badge variant="outline" className="text-[10px]">
                  Coming soon
                </Badge>
              </div>
            </button>
            <Link
              to="/upload"
              className="block w-full text-left p-3 rounded-lg border border-zinc-800/60 bg-zinc-900/30 hover:bg-zinc-900/60 transition-colors group"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">Bulk upload</div>
                  <div className="text-xs text-zinc-500 mt-0.5">
                    Push 10+ beats at once
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-zinc-600 group-hover:text-zinc-300 transition-colors" />
              </div>
            </Link>
            <button className="w-full text-left p-3 rounded-lg border border-zinc-800/60 bg-zinc-900/30 hover:bg-zinc-900/60 transition-colors group">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">Schedule release</div>
                  <div className="text-xs text-zinc-500 mt-0.5">Drop at a specific time</div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-zinc-600 group-hover:text-zinc-300 transition-colors" />
              </div>
            </button>
            <Link
              to="/platforms"
              className="block w-full text-left p-3 rounded-lg border border-zinc-800/60 bg-zinc-900/30 hover:bg-zinc-900/60 transition-colors group"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">Connect a platform</div>
                  <div className="text-xs text-zinc-500 mt-0.5">
                    {pendingPlatforms} awaiting setup
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-zinc-600 group-hover:text-zinc-300 transition-colors" />
              </div>
            </Link>
          </CardContent>
        </Card>
      </FadeUp>
    </>
  );
}
