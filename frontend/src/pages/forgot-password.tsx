import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { CheckCircle2, Disc3, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.auth.forgotPassword(email);
      setSent(true);
    } catch (err) {
      // We respond 202 on the happy path even when the email doesn't exist —
      // anything that reaches this branch is a real failure (rate limit, network).
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
            Reset your password
          </h1>
          <p className="text-sm text-zinc-500 mt-1 text-center">
            We'll email you a link to choose a new one.
          </p>
        </div>

        <div className="rounded-xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900/40 to-zinc-900/20 p-6 space-y-4 shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset,0_30px_60px_-30px_rgba(0,0,0,0.6)]">
          {sent ? (
            <div className="text-sm text-zinc-300 space-y-3">
              <div className="flex items-start gap-2.5 text-emerald-300">
                <CheckCircle2 className="h-4 w-4 mt-0.5" />
                <div>
                  If an account exists for{" "}
                  <span className="font-mono text-zinc-200">{email}</span>,
                  we just sent a reset link there.
                </div>
              </div>
              <div className="text-xs text-zinc-500">
                The link expires in 30 minutes. Check your spam folder if you
                don't see it.
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-zinc-400">Email</label>
                <Input
                  type="email"
                  required
                  autoComplete="email"
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </div>

              {error && (
                <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
                  {error}
                </div>
              )}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Sending...
                  </>
                ) : (
                  "Send reset link"
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
