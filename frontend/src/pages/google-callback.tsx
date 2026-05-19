import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, AlertCircle } from "lucide-react";
import { motion } from "motion/react";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";

/**
 * Receives the token in the URL fragment after Google OAuth.
 * Fragment chosen over query string so the JWT never appears in server logs.
 */
export function GoogleCallbackPage() {
  const navigate = useNavigate();
  const { loginWithToken } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    const params = new URLSearchParams(hash);
    const status = params.get("status");
    const token = params.get("token");
    const detail = params.get("detail");

    if (status === "ok" && token) {
      loginWithToken(token)
        .then(() => {
          // Wipe the fragment from history so the token can't be re-used by going back
          navigate("/", { replace: true });
        })
        .catch(() => setError("Couldn't verify sign-in"));
      return;
    }

    setError(detail ?? "Sign-in failed");
  }, [loginWithToken, navigate]);

  return (
    <div className="min-h-screen w-screen flex items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-sm text-center"
      >
        {error ? (
          <>
            <div className="h-11 w-11 rounded-full bg-amber-950/40 border border-amber-900/50 flex items-center justify-center mx-auto mb-4">
              <AlertCircle className="h-5 w-5 text-amber-300" />
            </div>
            <h1 className="text-lg font-semibold tracking-tight">Sign-in failed</h1>
            <p className="text-sm text-zinc-500 mt-1">{error}</p>
            <Button
              size="sm"
              variant="outline"
              className="mt-6"
              onClick={() => navigate("/login", { replace: true })}
            >
              Back to sign in
            </Button>
          </>
        ) : (
          <>
            <Loader2 className="h-5 w-5 text-zinc-400 animate-spin mx-auto mb-3" />
            <p className="text-sm text-zinc-400">Finishing sign-in...</p>
          </>
        )}
      </motion.div>
    </div>
  );
}
