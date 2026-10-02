import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { IS_DESKTOP } from "@/lib/target";
import { Button } from "@/components/ui/button";

export function AuthGate() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center">
        <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    // Desktop has no login page — not "authenticated" means the local backend
    // didn't answer /auth/me. Offer a reload instead of a redirect loop.
    if (IS_DESKTOP) {
      return (
        <div className="h-screen w-screen flex flex-col items-center justify-center gap-3 text-sm">
          <p className="text-zinc-400">Couldn't reach the Beatuploader engine.</p>
          <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
            Retry
          </Button>
        </div>
      );
    }
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
