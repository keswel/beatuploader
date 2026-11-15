import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Analytics } from "@vercel/analytics/react";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { IS_DESKTOP } from "./lib/target";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        // Don't retry auth failures
        const status = (error as { status?: number })?.status;
        if (status === 401 || status === 403) return false;
        return failureCount < 2;
      },
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <App />
        </AuthProvider>
        {/* Website visitor counts (Vercel Web Analytics: cookieless, bots
            filtered). Never in the desktop app, which promises no tracking. */}
        {!IS_DESKTOP && <Analytics />}
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
);
