import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api";

/**
 * Below this the signup count stays hidden; a public "3 producers" reads as empty.
 * The server already rounds the count down to a multiple of 5, hence "25+".
 */
const COUNT_SHOWN_FROM = 25;

/**
 * Email-only signup for early releases. Posts to the hosted backend's /waitlist.
 * Used on the landing page (with a link to /early-access) and on that page itself.
 */
export function EarlyReleaseSignup({
  id,
  title = "Early release",
  showWhyLink = false,
}: {
  id?: string;
  title?: string;
  showWhyLink?: boolean;
}) {
  const inputId = useId();
  const errorId = useId();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [error, setError] = useState("");
  const qc = useQueryClient();
  // Stays hidden until it loads (or if it fails), so a cold backend never shows "0".
  const { data } = useQuery({
    queryKey: ["waitlist-count"],
    queryFn: api.waitlist.count,
    staleTime: 60_000,
  });
  const count = data?.count ?? 0;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setState("sending");
    try {
      await api.waitlist.join(email.trim());
      setState("done");
      qc.invalidateQueries({ queryKey: ["waitlist-count"] });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? "Too many tries. Wait a few minutes and try again."
          : err instanceof ApiError && err.status === 422
            ? "That doesn't look like an email address."
            : "Couldn't sign you up. Try again in a moment.",
      );
      setState("error");
    }
  };

  return (
    <div className="paper early" id={id}>
      <div className="early-head">
        <h2>{title}</h2>
        <span className="early-count" aria-live="polite">
          {count >= COUNT_SHOWN_FROM ? (
            <>
              <b>{count.toLocaleString()}+</b> producers on the list
            </>
          ) : (
            "Be one of the first"
          )}
        </span>
      </div>
      {state === "done" ? (
        <p role="status">You're on the list. We'll email you when there's something to try.</p>
      ) : (
        <>
          <p>
            Leave your email to get new versions before everyone else. The
            first 50 people get Premium free for life.
            {showWhyLink && (
              <>
                {" "}
                <Link to="/early-access" className="early-why">What you get</Link>
              </>
            )}
          </p>
          <form className="early-form" onSubmit={onSubmit}>
            <label htmlFor={inputId} className="sr-only">Email address</label>
            <input
              id={inputId}
              type="email"
              required
              maxLength={254}
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={state === "error" || undefined}
              aria-describedby={state === "error" ? errorId : undefined}
            />
            <button className="btn" type="submit" disabled={state === "sending"}>
              {state === "sending" ? "Signing up…" : "Sign up"}
            </button>
          </form>
          {state === "error" && (
            <p id={errorId} className="early-error" role="alert">{error}</p>
          )}
          <p className="early-fine">
            We only email about early releases and Premium. No spam, and you can
            ask to be removed any time.{" "}
            <Link to="/terms#founding-members">Founding member terms</Link>
          </p>
        </>
      )}
    </div>
  );
}
