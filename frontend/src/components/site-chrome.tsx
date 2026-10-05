import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { paintSky, SKY_PRESETS } from "@/lib/collage-sky";
import "@/pages/landing.css";

// Shared pieces of the public website (landing + legal pages): fonts, header,
// footer and the generated-sky section. Styles live in pages/landing.css.

const FONTS_URL =
  "https://fonts.googleapis.com/css2?family=Bodoni+Moda:ital,opsz,wght@0,6..96,400..900;1,6..96,400..900&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap";

/** React 19 hoists this into <head>; only the website needs these faces. */
export function SiteFonts() {
  return <link rel="stylesheet" href={FONTS_URL} precedence="default" />;
}

export function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="top">
      <div className="wrap">
        <Link to="/" className="brand">
          <img src="/logo-wave.svg" alt="" aria-hidden draggable={false} />
          beatuploader
        </Link>
        <nav>{children}</nav>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer>
      <div className="wrap">
        <span>© {new Date().getFullYear()} Beatuploader</span>
        <Link to="/privacy">Privacy</Link>
        <Link to="/terms">Terms</Link>
        <a href="mailto:hello@beatuploader.app">Contact</a>
      </div>
    </footer>
  );
}

/** A section whose background is a generated sky, repainted when its size changes. */
export function Collage({
  preset,
  className,
  id,
  children,
}: {
  preset: keyof typeof SKY_PRESETS;
  className: string;
  id?: string;
  children: ReactNode;
}) {
  const sectionRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    const canvas = canvasRef.current;
    if (!section || !canvas) return;
    let last = { w: 0, h: 0 };
    const paint = () => {
      const w = section.offsetWidth, h = section.offsetHeight;
      // Skip small changes (mobile URL bar) so the noise isn't recomputed constantly.
      if (Math.abs(w - last.w) < 40 && Math.abs(h - last.h) < 40) return;
      last = { w, h };
      paintSky(canvas, w * 1.12, h, SKY_PRESETS[preset]); // canvas is 112% wide for the drift
    };
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(section);
    return () => ro.disconnect();
  }, [preset]);

  return (
    <section ref={sectionRef} id={id} className={`collage ${className}`}>
      <canvas ref={canvasRef} className="sky" aria-hidden />
      {children}
    </section>
  );
}
