import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import { Check, CheckCircle2, Disc3, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import {
  PASSWORD_MIN_LENGTH,
  checkPassword,
  isPasswordValid,
} from "@/lib/password";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();

  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checks = useMemo(() => checkPassword(next), [next]);
  const strong = useMemo(() => isPasswordValid(next), [next]);
  const valid = strong && next === confirm;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Reset link is missing its token. Request a new one.");
      return;
    }
    if (!valid) return;
    setSubmitting(true);
    try {
      await api.auth.resetPassword({ token, new_password: next });
      setDone(true);
      // Slight pause so the user reads the success state before we bounce.
      setTimeout(() => navigate("/login", { replace: true }), 1800);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen w-screen flex items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-sm"
      >
        <div className="flex flex-col items-center mb-8">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950 shadow-[0_0_40px_-6px_rgba(255,255,255,0.3)] mb-4">
            <Disc3 className="h-5 w-5" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">
            Choose a new password
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Existing sessions will be signed out.
          </p>
        </div>

        <div className="rounded-xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900/40 to-zinc-900/20 p-6 space-y-4 shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset,0_30px_60px_-30px_rgba(0,0,0,0.6)]">
          {done ? (
            <div className="flex items-start gap-2.5 text-emerald-300 text-sm">
              <CheckCircle2 className="h-4 w-4 mt-0.5" />
              <div>
                Password updated. Redirecting you to sign in...
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400">
                  New password
                </label>
                <Input
                  type="password"
                  required
                  autoComplete="new-password"
                  autoFocus
                  minLength={PASSWORD_MIN_LENGTH}
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                  placeholder="••••••••"
                />
                {next.length > 0 && <PasswordChecklist checks={checks} />}
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400">
                  Confirm new password
                </label>
                <Input
                  type="password"
                  required
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  placeholder="••••••••"
                  className={
                    confirm.length > 0 && next !== confirm
                      ? "border-red-900/60 focus:border-red-700"
                      : ""
                  }
                />
              </div>

              {error && (
                <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
                  {error}
                </div>
              )}

              <Button
                type="submit"
                className="w-full"
                disabled={submitting || !valid}
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Updating...
                  </>
                ) : (
                  "Update password"
                )}
              </Button>
            </form>
          )}
        </div>

        <div className="mt-6 text-center text-sm text-zinc-500">
          <Link
            to="/login"
            className="text-zinc-200 hover:text-zinc-50 font-medium transition-colors"
          >
            Back to sign in
          </Link>
        </div>
      </motion.div>
    </div>
  );
}

function PasswordChecklist({
  checks,
}: {
  checks: ReturnType<typeof checkPassword>;
}) {
  const items: { ok: boolean; label: string }[] = [
    { ok: checks.length, label: `${PASSWORD_MIN_LENGTH}+ characters` },
    { ok: checks.upper, label: "Uppercase letter" },
    { ok: checks.lower, label: "Lowercase letter" },
    { ok: checks.digit, label: "Number" },
    { ok: checks.special, label: "Special character" },
  ];
  return (
    <ul className="grid grid-cols-2 gap-x-3 gap-y-1 pt-2 text-[10px]">
      {items.map((it) => (
        <li
          key={it.label}
          className={`flex items-center gap-1.5 ${
            it.ok ? "text-emerald-400" : "text-zinc-500"
          }`}
        >
          {it.ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
          {it.label}
        </li>
      ))}
    </ul>
  );
}
