import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Mail, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * Inline banner shown above the dashboard until the user verifies their email.
 *
 * Not blocking — we don't gate features on this yet (test users shouldn't be
 * locked out by an SMTP misconfig). Just nudges + offers a resend.
 *
 * Local-storage dismiss flag survives across page navigations but resets when
 * the user actually verifies (the banner stops rendering for verified users).
 */
const DISMISS_KEY = "beatuploader.verify-banner-dismissed";

export function VerifyEmailBanner() {
  const { user, refresh } = useAuth();
  const [dismissed, setDismissed] = useState<boolean>(
    () => localStorage.getItem(DISMISS_KEY) === "1",
  );
  const [resending, setResending] = useState(false);
  const [resendStatus, setResendStatus] =
    useState<"idle" | "sent" | "already" | "error">("idle");

  if (!user) return null;
  if (user.email_verified_at) return null;
  if (dismissed) return null;

  const handleResend = async () => {
    setResending(true);
    setResendStatus("idle");
    try {
      const res = await api.auth.resendVerification();
      if (res.status === "already_verified") {
        setResendStatus("already");
        // Refresh in case our local user object is stale.
        refresh().catch(() => undefined);
      } else {
        setResendStatus("sent");
      }
    } catch (err) {
      setResendStatus("error");
      if (err instanceof ApiError && err.status === 429) {
        setResendStatus("error");
      }
    } finally {
      setResending(false);
    }
  };

  const dismiss = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="mb-6 rounded-lg border border-amber-900/40 bg-amber-950/20 px-4 py-3 flex items-center gap-3 text-xs"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-900/30 border border-amber-900/40 shrink-0">
          <Mail className="h-3.5 w-3.5 text-amber-300" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-zinc-200 font-medium">
            Verify your email
          </div>
          <div className="text-zinc-500 mt-0.5">
            {resendStatus === "sent"
              ? `We just resent the link to ${user.email}. Check your inbox.`
              : resendStatus === "already"
                ? "Your email is already verified."
                : resendStatus === "error"
                  ? "Couldn't resend right now. Try again in a few minutes."
                  : `We sent a link to ${user.email}. Open it to confirm.`}
          </div>
        </div>
        <button
          type="button"
          onClick={handleResend}
          disabled={resending || resendStatus === "sent"}
          className="text-xs font-medium text-amber-200 hover:text-amber-100 disabled:opacity-50 disabled:pointer-events-none transition-colors shrink-0"
        >
          {resending ? "Sending..." : "Resend"}
        </button>
        <button
          type="button"
          onClick={dismiss}
          className="text-zinc-500 hover:text-zinc-300 transition-colors shrink-0"
          aria-label="Dismiss"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </motion.div>
    </AnimatePresence>
  );
}
