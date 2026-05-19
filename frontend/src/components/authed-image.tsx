import { useEffect, useState, type ReactNode } from "react";
import { getToken } from "@/lib/api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api";

// Cache blob URLs per source path so we don't re-fetch the same image when a row
// re-renders or when multiple rows reference the same artwork.
const cache = new Map<string, Promise<string>>();

function fetchBlobUrl(path: string): Promise<string> {
  const existing = cache.get(path);
  if (existing) return existing;
  const token = getToken();
  const url = `${API_BASE}${path}`;
  const p = fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
    .then((r) => {
      if (!r.ok) throw new Error(`fetch ${path}: ${r.status}`);
      return r.blob();
    })
    .then((b) => URL.createObjectURL(b));
  cache.set(path, p);
  // If the fetch fails, drop the cached promise so we'll retry next time
  p.catch(() => cache.delete(path));
  return p;
}

interface Props {
  /** Path relative to API_BASE, e.g. "/uploads/42/artwork". */
  src: string | null | undefined;
  alt?: string;
  className?: string;
  fallback: ReactNode;
}

/**
 * <img> that fetches with auth header and shows via blob URL. Used for endpoints
 * that require Bearer auth (browsers can't attach headers to a plain <img src>).
 *
 * Falls back to `fallback` when src is null or the fetch fails.
 */
export function AuthedImage({ src, alt, className, fallback }: Props) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [errored, setErrored] = useState(false);

  useEffect(() => {
    if (!src) {
      setBlobUrl(null);
      setErrored(false);
      return;
    }
    let cancelled = false;
    setErrored(false);
    fetchBlobUrl(src)
      .then((url) => {
        if (!cancelled) setBlobUrl(url);
      })
      .catch(() => {
        if (!cancelled) setErrored(true);
      });
    return () => {
      cancelled = true;
    };
  }, [src]);

  if (!src || errored || !blobUrl) {
    return <>{fallback}</>;
  }
  return <img src={blobUrl} alt={alt ?? ""} className={className} />;
}
