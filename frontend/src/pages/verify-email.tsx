import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import { AlertCircle, CheckCircle2, Disc3, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type State =
  | { kind: "verifying" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { refresh } = useAuth();
  const [state, setState] = useState<State>({ kind: "verifying" });

  useEffect(() => {
    if (!token) {
      setState({
        kind: "error",
        message: "This verification link is missing its token.",
      });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        await api.auth.verifyEmail(token);
        if (cancelled) return;
        setState({ kind: "ok" });
        // Refresh /me so the dashboard banner disappears if the user is signed in.
        refresh().catch(() => undefined);
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            err instanceof ApiError
              ? err.detail
              : "Something went wrong verifying your email.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, refresh]);

  return (
    <div className="min-h-screen w-screen flex items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-sm text-center"
      >
        <div className="flex flex-col items-center mb-6">
          <Link to="/" className="mb-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950 shadow-[0_0_30px_-6px_rgba(255,255,255,0.3)]">
              <Disc3 className="h-4 w-4" />
            </div>
          </Link>
        </div>

        {state.kind === "verifying" && (
          <>
            <Loader2 className="h-5 w-5 text-zinc-400 animate-spin mx-auto mb-3" />
            <p className="text-sm text-zinc-400">Verifying your email...</p>
          </>
        )}

        {state.kind === "ok" && (
          <>
            <div className="h-11 w-11 rounded-full bg-emerald-950/40 border border-emerald-900/50 flex items-center justify-center mx-auto mb-4">
              <CheckCircle2 className="h-5 w-5 text-emerald-300" />
            </div>
            <h1 className="text-lg font-semibold tracking-tight">
              Email confirmed
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              Thanks — you're all set.
            </p>
            <Button size="sm" className="mt-6" asChild>
              <Link to="/dashboard">Go to dashboard</Link>
            </Button>
          </>
        )}

        {state.kind === "error" && (
          <>
            <div className="h-11 w-11 rounded-full bg-amber-950/40 border border-amber-900/50 flex items-center justify-center mx-auto mb-4">
              <AlertCircle className="h-5 w-5 text-amber-300" />
            </div>
            <h1 className="text-lg font-semibold tracking-tight">
              Couldn't verify
            </h1>
            <p className="text-sm text-zinc-500 mt-1">{state.message}</p>
            <p className="text-xs text-zinc-600 mt-4">
              Sign in and resend the verification email from your dashboard.
            </p>
            <Button size="sm" variant="outline" className="mt-6" asChild>
              <Link to="/login">Back to sign in</Link>
            </Button>
          </>
        )}
      </motion.div>
    </div>
  );
}
