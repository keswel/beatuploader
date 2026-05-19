import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BeatStarsCredentialsDialog({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: api.platforms.beatstarsCredentials,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["platforms"] });
      onOpenChange(false);
      setUsername("");
      setPassword("");
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Failed to connect");
    },
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    mutation.mutate({ username, password });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect BeatStars</DialogTitle>
          <DialogDescription>
            BeatStars has no public API, so we log in on your behalf. Your password is
            encrypted at rest and only used to keep your session alive.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-md border border-zinc-800/80 bg-zinc-900/40 px-3 py-2.5 flex items-start gap-2.5 text-xs text-zinc-400">
          <Lock className="h-3.5 w-3.5 mt-0.5 text-zinc-500 shrink-0" />
          <div>
            Heads up: BeatStars doesn't officially support automation. If you have 2FA
            enabled on your BeatStars account, disable it before connecting.
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">
              BeatStars email
            </label>
            <Input
              type="email"
              autoComplete="off"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">
              BeatStars password
            </label>
            <Input
              type="password"
              autoComplete="off"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
              {error}
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={mutation.isPending}>
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Connecting...
                </>
              ) : (
                "Connect"
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
