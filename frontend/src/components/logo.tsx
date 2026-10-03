import { cn } from "@/lib/utils";

/** The "bu" + wave brand mark (public/logo-mark.svg, cropped from brand/logo.svg).
 *  Decorative — pair it with the "Beatuploader" wordmark for the accessible name. */
export function Logo({ className }: { className?: string }) {
  return (
    <img
      src="/logo-mark.svg"
      alt=""
      aria-hidden
      draggable={false}
      className={cn("h-5 w-auto select-none", className)}
    />
  );
}
