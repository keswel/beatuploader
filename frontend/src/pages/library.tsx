import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import {
  Music2,
  MoreHorizontal,
  Search,
  Filter,
  Download,
  CheckCircle2,
  AlertCircle,
  Clock,
  MinusCircle,
  Loader2,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { cn, formatDate } from "@/lib/utils";
import { api } from "@/lib/api";
import type { BeatPlatformStatus, PlatformProvider } from "@/lib/types";

const platformLabels: Record<PlatformProvider, string> = {
  beatstars: "BS",
  youtube: "YT",
  soundcloud: "SC",
  spotify: "SP",
  audiomack: "AM",
  bandcamp: "BC",
};

const visibleProviders: PlatformProvider[] = [
  "beatstars",
  "youtube",
  "soundcloud",
  "spotify",
];

function StatusDot({ status }: { status: BeatPlatformStatus }) {
  const map = {
    live: { Icon: CheckCircle2, className: "text-emerald-400" },
    uploading: { Icon: Clock, className: "text-amber-400 animate-pulse" },
    failed: { Icon: AlertCircle, className: "text-red-400" },
    none: { Icon: MinusCircle, className: "text-zinc-700" },
  };
  const { Icon, className } = map[status];
  return <Icon className={cn("h-3.5 w-3.5", className)} />;
}

export function LibraryPage() {
  const [query, setQuery] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["library", query],
    queryFn: () => api.library.list({ q: query || undefined, limit: 50 }),
  });

  const beats = data ?? [];

  return (
    <>
      <PageHeader
        title="Library"
        description="Every beat you've shipped, across every platform."
        actions={
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        }
      />

      <Card>
        <CardContent className="p-0">
          <div className="flex items-center gap-3 px-5 py-3.5 border-b border-zinc-800/60">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search title or tag..."
                className="w-full h-9 rounded-md border border-zinc-800/80 bg-zinc-900/30 pl-9 pr-3 text-sm placeholder:text-zinc-500 focus:outline-none focus:border-zinc-700 focus:bg-zinc-900/60 transition-colors"
              />
            </div>
            <Button variant="outline" size="sm">
              <Filter className="h-3.5 w-3.5" />
              Filter
            </Button>
            <div className="ml-auto text-xs text-zinc-500 tabular-nums">
              {beats.length} {beats.length === 1 ? "beat" : "beats"}
            </div>
          </div>

          {isLoading && (
            <div className="flex justify-center py-12">
              <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
            </div>
          )}

          {error && (
            <div className="px-5 py-12 text-center text-sm text-red-300">
              Couldn't load library.
            </div>
          )}

          {!isLoading && !error && beats.length === 0 && (
            <div className="px-5 py-16 text-center">
              <Music2 className="h-8 w-8 text-zinc-700 mx-auto mb-3" />
              <div className="text-sm font-medium text-zinc-300">No beats yet</div>
              <div className="mt-1 text-xs text-zinc-500">
                Upload your first beat to start your library.
              </div>
            </div>
          )}

          {!isLoading && !error && beats.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800/60">
                    <th className="font-medium px-5 py-3">Title</th>
                    <th className="font-medium px-3 py-3">BPM</th>
                    <th className="font-medium px-3 py-3">Key</th>
                    <th className="font-medium px-3 py-3">Tags</th>
                    <th className="font-medium px-3 py-3">Platforms</th>
                    <th className="font-medium px-3 py-3 text-right">Plays</th>
                    <th className="font-medium px-3 py-3">Released</th>
                    <th className="px-3 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {beats.map((beat, i) => (
                    <motion.tr
                      key={beat.id}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.025, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                      className="hover:bg-zinc-900/30 transition-colors duration-200"
                    >
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-md bg-gradient-to-br from-zinc-800 to-zinc-900 ring-1 ring-zinc-800 flex items-center justify-center shrink-0">
                            <Music2 className="h-3.5 w-3.5 text-zinc-500" />
                          </div>
                          <span className="font-medium">{beat.title}</span>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-zinc-400 tabular-nums">
                        {beat.bpm ?? "—"}
                      </td>
                      <td className="px-3 py-3 text-zinc-400 font-mono text-xs">
                        {beat.music_key ?? "—"}
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex flex-wrap gap-1">
                          {beat.tags.slice(0, 2).map((tag) => (
                            <Badge key={tag} variant="secondary" className="text-[10px]">
                              {tag}
                            </Badge>
                          ))}
                          {beat.tags.length > 2 && (
                            <span className="text-[10px] text-zinc-500 self-center">
                              +{beat.tags.length - 2}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2">
                          {visibleProviders.map((p) => (
                            <div key={p} className="flex flex-col items-center gap-0.5">
                              <StatusDot status={beat.platform_statuses[p] ?? "none"} />
                              <span className="text-[9px] text-zinc-600 font-medium">
                                {platformLabels[p]}
                              </span>
                            </div>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {beat.plays.toLocaleString()}
                      </td>
                      <td className="px-3 py-3 text-zinc-400">
                        {beat.released_at ? formatDate(beat.released_at) : "—"}
                      </td>
                      <td className="px-3 py-3">
                        <Button variant="ghost" size="icon" className="h-7 w-7">
                          <MoreHorizontal className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
