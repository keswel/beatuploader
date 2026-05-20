import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock, Smartphone } from "lucide-react";
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

type Stage =
  | { kind: "credentials" }
  | { kind: "sms"; challengeId: string; hint: string };

export function BeatStarsCredentialsDialog({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState<Stage>({ kind: "credentials" });
  const [error, setError] = useState<string | null>(null);

  const resetAll = () => {
    setUsername("");
    setPassword("");
    setCode("");
    setStage({ kind: "credentials" });
    setError(null);
  };

  const credentialsMutation = useMutation({
    mutationFn: api.platforms.beatstarsCredentials,
    onSuccess: (data) => {
      if (data.status === "sms_required") {
        setStage({
          kind: "sms",
          challengeId: data.challenge_id,
          hint: data.hint,
        });
        setError(null);
        return;
      }
      qc.invalidateQueries({ queryKey: ["platforms"] });
      onOpenChange(false);
      resetAll();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Failed to connect");
    },
  });

  const smsMutation = useMutation({
    mutationFn: api.platforms.beatstarsSms,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["platforms"] });
      onOpenChange(false);
      resetAll();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Couldn't verify the code");
    },
  });

  const submitCredentials = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    credentialsMutation.mutate({ username, password });
  };

  const submitSms = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (stage.kind !== "sms") return;
    smsMutation.mutate({ challenge_id: stage.challengeId, code });
  };

  const handleOpenChange = (next: boolean) => {
    if (!next && stage.kind === "sms") {
      // User dismissed the dialog mid-challenge — tell the server to drop it
      // so the parked browser closes promptly.
      api.platforms.beatstarsSmsCancel(stage.challengeId).catch(() => {});
    }
    onOpenChange(next);
    if (!next) resetAll();
  };

  const isSms = stage.kind === "sms";
  const busy = credentialsMutation.isPending || smsMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isSms ? "Verify your phone" : "Connect BeatStars"}
          </DialogTitle>
          <DialogDescription>
            {isSms
              ? stage.hint ||
                "BeatStars sent a verification code to your phone."
              : "BeatStars has no public API, so we log in on your behalf. Your password is encrypted at rest and only used to keep your session alive."}
          </DialogDescription>
        </DialogHeader>

        {!isSms && (
          <div className="rounded-md border border-zinc-800/80 bg-zinc-900/40 px-3 py-2.5 flex items-start gap-2.5 text-xs text-zinc-400">
            <Lock className="h-3.5 w-3.5 mt-0.5 text-zinc-500 shrink-0" />
            <div>
              If BeatStars challenges us with SMS 2FA, we'll prompt you for the
              code on the next step.
            </div>
          </div>
        )}

        {isSms && (
          <div className="rounded-md border border-zinc-800/80 bg-zinc-900/40 px-3 py-2.5 flex items-start gap-2.5 text-xs text-zinc-400">
            <Smartphone className="h-3.5 w-3.5 mt-0.5 text-zinc-500 shrink-0" />
            <div>
              Enter the 6-digit code BeatStars just sent you. The live login
              session stays open server-side for ~5 minutes.
            </div>
          </div>
        )}

        {!isSms ? (
          <form onSubmit={submitCredentials} className="space-y-4">
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
                onClick={() => handleOpenChange(false)}
                disabled={busy}
              >
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={busy}>
                {credentialsMutation.isPending ? (
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
        ) : (
          <form onSubmit={submitSms} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">
                Verification code
              </label>
              <Input
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="one-time-code"
                autoFocus
                required
                value={code}
                onChange={(e) =>
                  setCode(e.target.value.replace(/\D/g, "").slice(0, 8))
                }
                placeholder="123456"
                className="font-mono tracking-[0.4em] text-center text-lg"
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
                onClick={() => handleOpenChange(false)}
                disabled={busy}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={busy || code.length < 4}
              >
                {smsMutation.isPending ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  "Verify"
                )}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
