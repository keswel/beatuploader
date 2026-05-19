import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import { Disc3, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";

type Mode = "login" | "register";

export function LoginPage() {
  const { isAuthenticated, isLoading: authLoading, login, register } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [handle, setHandle] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  const startGoogle = async () => {
    setError(null);
    setGoogleLoading(true);
    try {
      const { authorize_url } = await api.auth.googleStart();
      window.location.href = authorize_url;
    } catch (err) {
      setGoogleLoading(false);
      setError(err instanceof ApiError ? err.detail : "Google sign-in unavailable");
    }
  };

  if (!authLoading && isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, handle, password);
      }
      navigate("/", { replace: true });
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
          <motion.div
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.5, ease: [0.32, 0.72, 0, 1] }}
            className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950 shadow-[0_0_40px_-6px_rgba(255,255,255,0.3)] mb-4"
          >
            <Disc3 className="h-5 w-5" />
          </motion.div>
          <h1 className="text-xl font-semibold tracking-tight">
            {mode === "login" ? "Sign in" : "Create your account"}
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            {mode === "login"
              ? "Welcome back to Beatuploader"
              : "Start uploading beats everywhere at once"}
          </p>
        </div>

        <div className="rounded-xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900/40 to-zinc-900/20 p-6 space-y-4 shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset,0_30px_60px_-30px_rgba(0,0,0,0.6)]">
          <Button
            type="button"
            variant="secondary"
            className="w-full h-10 bg-white hover:bg-zinc-100 text-zinc-900 border-zinc-200 font-medium"
            onClick={startGoogle}
            disabled={googleLoading || submitting}
          >
            {googleLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <GoogleLogo />
            )}
            Continue with Google
          </Button>

          <div className="relative flex items-center my-2">
            <div className="flex-1 h-px bg-zinc-800/80" />
            <span className="px-3 text-[10px] uppercase tracking-widest text-zinc-600">
              or
            </span>
            <div className="flex-1 h-px bg-zinc-800/80" />
          </div>

          <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Email</label>
            <Input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>

          {mode === "register" && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              transition={{ duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
              className="space-y-1.5 overflow-hidden"
            >
              <label className="text-xs font-medium text-zinc-400">Handle</label>
              <Input
                required
                minLength={2}
                pattern="[a-zA-Z0-9_.\-]+"
                value={handle}
                onChange={(e) => setHandle(e.target.value)}
                placeholder="producerhandle"
              />
              <div className="text-[10px] text-zinc-600 pt-1">
                Letters, numbers, _ . - only
              </div>
            </motion.div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-zinc-400">Password</label>
            <Input
              type="password"
              required
              minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2"
            >
              {error}
            </motion.div>
          )}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {mode === "login" ? "Signing in..." : "Creating account..."}
                </>
              ) : (
                <>{mode === "login" ? "Sign in" : "Create account"}</>
              )}
            </Button>
          </form>
        </div>

        <div className="mt-6 text-center text-sm text-zinc-500">
          {mode === "login" ? (
            <>
              Don't have an account?{" "}
              <button
                type="button"
                onClick={() => setMode("register")}
                className="text-zinc-200 hover:text-zinc-50 font-medium transition-colors"
              >
                Sign up
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => setMode("login")}
                className="text-zinc-200 hover:text-zinc-50 font-medium transition-colors"
              >
                Sign in
              </button>
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
}

function GoogleLogo() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18A10.97 10.97 0 0 0 1 12c0 1.77.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}
