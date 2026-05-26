import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Youtube,
  Music,
  Cloud,
  Disc,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Settings2,
  Loader2,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { Stagger, StaggerItem } from "@/components/motion";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { PlatformOut, PlatformProvider } from "@/lib/types";
import { BeatStarsCredentialsDialog } from "@/components/beatstars-credentials-dialog";

interface PresentationMeta {
  description: string;
  icon: React.ElementType;
  accent: string;
  method: "API" | "Headless" | "OAuth";
  displayName: string;
}

const presentation: Record<PlatformProvider, PresentationMeta> = {
  youtube: {
    displayName: "YouTube",
    description: "Official Data API v3 with OAuth",
    icon: Youtube,
    accent: "from-red-600/20 to-red-600/0",
    method: "OAuth",
  },
  soundcloud: {
    displayName: "SoundCloud",
    description: "OAuth 2.1 — uploads and metadata",
    icon: Cloud,
    accent: "from-orange-500/20 to-orange-500/0",
    method: "OAuth",
  },
  beatstars: {
    displayName: "BeatStars",
    description: "Headless automation — no public API",
    icon: Disc,
    accent: "from-red-500/20 to-red-500/0",
    method: "Headless",
  },
  spotify: {
    displayName: "Spotify",
    description: "Via DistroKid relay — splits & royalties",
    icon: Music,
    accent: "from-emerald-500/20 to-emerald-500/0",
    method: "API",
  },
  audiomack: {
    displayName: "Audiomack",
    description: "OAuth 2.0 — uploads, plays, royalties",
    icon: Music,
    accent: "from-amber-500/20 to-amber-500/0",
    method: "OAuth",
  },
  bandcamp: {
    displayName: "Bandcamp",
    description: "Headless — direct sales and downloads",
    icon: Disc,
    accent: "from-sky-500/20 to-sky-500/0",
    method: "Headless",
  },
};

const statusMap = {
  connected: {
    label: "Connected",
    badge: "success" as const,
    icon: CheckCircle2,
    iconClass: "text-emerald-400",
  },
  disconnected: {
    label: "Not connected",
    badge: "outline" as const,
    icon: AlertCircle,
    iconClass: "text-zinc-500",
  },
  error: {
    label: "Reauth needed",
    badge: "warning" as const,
    icon: AlertCircle,
    iconClass: "text-amber-400",
  },
};

export function PlatformsPage() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [banner, setBanner] = useState<
    | { kind: "success" | "error"; provider: string; detail?: string }
    | null
  >(null);
  const [credentialsDialog, setCredentialsDialog] = useState<PlatformProvider | null>(
    null,
  );

  const { data, isLoading, error } = useQuery({
    queryKey: ["platforms"],
    queryFn: api.platforms.list,
  });

  const disconnect = useMutation({
    mutationFn: (provider: PlatformProvider) => api.platforms.disconnect(provider),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platforms"] }),
  });

  // Handle OAuth callback return: ?status=connected&provider=youtube OR ?status=error&detail=...
  useEffect(() => {
    const statusParam = params.get("status");
    const provider = params.get("provider");
    if (!statusParam || !provider) return;
    if (statusParam === "connected") {
      setBanner({ kind: "success", provider });
      qc.invalidateQueries({ queryKey: ["platforms"] });
    } else {
      setBanner({
        kind: "error",
        provider,
        detail: params.get("detail") ?? undefined,
      });
    }
    // Clean URL
    const next = new URLSearchParams(params);
    next.delete("status");
    next.delete("provider");
    next.delete("detail");
    setParams(next, { replace: true });
  }, [params, qc, setParams]);

  return (
    <>
      <PageHeader
        title="Platforms"
        description="Connect your accounts. We'll route uploads through the right method per platform."
        actions={
          <Button variant="outline" size="sm">
            Request integration
          </Button>
        }
      />

      <AnimatePresence>
        {banner && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
            className={cn(
              "mb-6 rounded-lg border px-4 py-3 flex items-center gap-3 text-sm",
              banner.kind === "success"
                ? "border-emerald-900/60 bg-emerald-950/40 text-emerald-200"
                : "border-amber-900/60 bg-amber-950/40 text-amber-200",
            )}
          >
            {banner.kind === "success" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" />
            )}
            <div className="flex-1">
              {banner.kind === "success" ? (
                <>
                  <span className="font-medium capitalize">{banner.provider}</span>{" "}
                  connected successfully.
                </>
              ) : (
                <>
                  Couldn't connect{" "}
                  <span className="font-medium capitalize">{banner.provider}</span>
                  {banner.detail ? `: ${banner.detail}` : "."}
                </>
              )}
            </div>
            <button
              type="button"
              onClick={() => setBanner(null)}
              className="opacity-60 hover:opacity-100 transition-opacity"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {isLoading && (
        <div className="flex justify-center py-16">
          <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
        </div>
      )}

      {error && (
        <Card className="p-6 text-sm text-red-300">
          Couldn't load platforms — is the backend running on port 8000?
        </Card>
      )}

      {data && (
        <Stagger
          stagger={0.05}
          className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
        >
          {data.map((p) => (
            <StaggerItem key={p.provider}>
              <PlatformCard
                platform={p}
                onDisconnect={() => disconnect.mutate(p.provider)}
                disconnecting={disconnect.isPending && disconnect.variables === p.provider}
                onCredentialsConnect={() => setCredentialsDialog(p.provider)}
              />
            </StaggerItem>
          ))}
        </Stagger>
      )}

      <BeatStarsCredentialsDialog
        open={credentialsDialog === "beatstars"}
        onOpenChange={(open) => setCredentialsDialog(open ? "beatstars" : null)}
      />
    </>
  );
}

interface PlatformCardProps {
  platform: PlatformOut;
  onDisconnect: () => void;
  disconnecting: boolean;
  onCredentialsConnect: () => void;
}

function PlatformCard({
  platform,
  onDisconnect,
  disconnecting,
  onCredentialsConnect,
}: PlatformCardProps) {
  const meta = presentation[platform.provider];
  const status = statusMap[platform.status];
  const Icon = meta.icon;
  const StatusIcon = status.icon;
  const comingSoon = !platform.configured;

  const [connecting, setConnecting] = useState(false);
  const handleConnect = async () => {
    if (comingSoon) return;
    if (meta.method === "Headless") {
      onCredentialsConnect();
      return;
    }
    setConnecting(true);
    try {
      const { authorize_url } = await api.platforms.connect(platform.provider);
      window.location.href = authorize_url;
    } catch (err) {
      setConnecting(false);
      alert(
        err instanceof Error
          ? err.message
          : `${meta.displayName} integration isn't wired up yet`,
      );
    }
  };

  return (
    <Card interactive className="relative overflow-hidden group h-full">
      <div
        className={cn(
          "absolute inset-0 bg-gradient-to-br opacity-50 pointer-events-none",
          meta.accent,
        )}
      />
      <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-zinc-700/50 to-transparent" />
      <CardContent className="relative p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="h-10 w-10 rounded-lg bg-zinc-900 ring-1 ring-zinc-800 flex items-center justify-center shadow-[0_0_20px_-6px_rgba(255,255,255,0.1)]">
            <Icon className="h-5 w-5 text-zinc-200" />
          </div>
          {comingSoon ? (
            <Badge variant="outline" className="gap-1 text-zinc-400">
              Coming soon
            </Badge>
          ) : (
            <Badge variant={status.badge} className="gap-1">
              <StatusIcon className={cn("h-2.5 w-2.5", status.iconClass)} />
              {status.label}
            </Badge>
          )}
        </div>

        <div className="text-base font-semibold tracking-tight">{meta.displayName}</div>
        <div className="mt-1 text-xs text-zinc-500 leading-relaxed">{meta.description}</div>

        <div className="mt-4 pt-4 border-t border-zinc-800/60 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-500">Method</span>
            <span className="font-mono text-zinc-300">{meta.method}</span>
          </div>
          {platform.account_label && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Account</span>
              <span className="text-zinc-300 truncate ml-2">{platform.account_label}</span>
            </div>
          )}
          {platform.last_error && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Last error</span>
              <span className="text-amber-300 truncate ml-2">{platform.last_error}</span>
            </div>
          )}
        </div>

        <div className="mt-4 flex items-center gap-2">
          {comingSoon && (
            <Button size="sm" className="flex-1" disabled>
              Coming soon
            </Button>
          )}
          {!comingSoon && platform.status === "connected" && (
            <>
              <Button variant="secondary" size="sm" className="flex-1">
                <Settings2 className="h-3.5 w-3.5" />
                Configure
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={onDisconnect}
                disabled={disconnecting}
              >
                {disconnecting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <ExternalLink className="h-3.5 w-3.5" />
                )}
              </Button>
            </>
          )}
          {!comingSoon && platform.status === "disconnected" && (
            <Button size="sm" className="flex-1" onClick={handleConnect} disabled={connecting}>
              {connecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Connect"}
            </Button>
          )}
          {!comingSoon && platform.status === "error" && (
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Reauthorize"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
