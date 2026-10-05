import { cn } from "@/lib/utils";

/** The wave brand mark (public/logo-wave.svg, the wave from brand/logo.svg).
 *  Decorative — pair it with the "Beatuploader" wordmark for the accessible name. */
export function Logo({ className }: { className?: string }) {
  return (
    <img
      src="/logo-wave.svg"
      alt=""
      aria-hidden
      draggable={false}
      className={cn("h-4 w-auto select-none", className)}
    />
  );
}
