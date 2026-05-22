import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowRight,
  Disc3,
  Music2,
  Plug,
  Sparkles,
  UploadCloud,
  Youtube,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

const easeOut = [0.22, 1, 0.36, 1] as const;

export function LandingPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();

  // Authenticated visitors get sent straight to their dashboard. Keep this in
  // a useEffect (not render-time Navigate) so the landing flashes briefly on
  // the way past — feels less abrupt for returning users.
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate("/dashboard", { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate]);

  return (
    <div className="min-h-screen w-full bg-zinc-950 text-zinc-100 relative overflow-hidden">
      <BackgroundGlow />

      <header className="relative z-10 mx-auto max-w-6xl px-6 py-6 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950 shadow-[0_0_20px_-4px_rgba(255,255,255,0.3)]">
            <Disc3 className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold tracking-tight">
            Beatuploader
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/login">Sign in</Link>
          </Button>
          <Button size="sm" asChild>
            <Link to="/login">
              Get started
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-6">
        <section className="pt-20 md:pt-32 pb-24 text-center">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: easeOut }}
            className="inline-flex items-center gap-1.5 rounded-full border border-zinc-800/80 bg-zinc-900/50 px-3 py-1 text-[11px] text-zinc-400 backdrop-blur"
          >
            <Sparkles className="h-3 w-3 text-zinc-500" />
            <span>One upload, every platform</span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.05, ease: easeOut }}
            className="mt-6 text-5xl md:text-7xl font-semibold tracking-tight leading-[1.05]"
          >
            Ship every beat
            <br />
            <span className="bg-gradient-to-b from-zinc-300 to-zinc-500 bg-clip-text text-transparent">
              everywhere at once.
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.12, ease: easeOut }}
            className="mt-6 max-w-xl mx-auto text-sm md:text-base text-zinc-400 leading-relaxed"
          >
            Drop your master, tagged MP3, stems and artwork once. Beatuploader
            pushes the right files to BeatStars, YouTube, and the rest — with
            the right licenses, the right metadata, and zero copy-paste.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.18, ease: easeOut }}
            className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3"
          >
            <Button size="lg" asChild>
              <Link to="/login">
                Start uploading
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <a href="#how">See how it works</a>
            </Button>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.3, ease: easeOut }}
            className="mt-6 text-[11px] text-zinc-600"
          >
            Free during beta · No credit card required
          </motion.p>
        </section>

        <section className="pb-24">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <FeatureCard
              icon={UploadCloud}
              title="Smart file routing"
              body="Master, tagged MP3, stems and cover art each go to the right place. We pick licenses automatically based on what you upload."
              delay={0}
            />
            <FeatureCard
              icon={Plug}
              title="Sessions stay warm"
              body="Connect BeatStars once with your login (we encrypt it). The Playwright session is reused across uploads — no re-auth, no 2FA on every push."
              delay={0.08}
            />
            <FeatureCard
              icon={Youtube}
              title="Type-beat ready"
              body="Auto-upload an unlisted YouTube video of the master with a description template. Drop {beatstars_link} in and we'll fill it in after BeatStars goes live."
              delay={0.16}
            />
          </div>
        </section>

        <section id="how" className="pb-24">
          <SectionLabel>How it works</SectionLabel>
          <h2 className="mt-3 text-3xl md:text-4xl font-semibold tracking-tight">
            Three steps. Then it's just dragging files in.
          </h2>
          <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
            <Step
              n={1}
              title="Connect"
              body="Sign in with Google to connect YouTube. Hand over your BeatStars login once — it's encrypted at rest with Fernet."
            />
            <Step
              n={2}
              title="Upload"
              body="Drag your beat's files into one box. We sort master/tagged/stems/artwork by extension and you're three fields away from publishing."
            />
            <Step
              n={3}
              title="Done"
              body="A real headless browser drives BeatStars end-to-end: file upload, license picks, price, publish. YouTube goes up as unlisted in parallel."
            />
          </div>
        </section>

        <section className="pb-32">
          <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900/60 to-zinc-900/20 p-10 md:p-14 text-center shadow-[0_30px_120px_-40px_rgba(0,0,0,0.8)]">
            <Music2 className="h-7 w-7 mx-auto text-zinc-500" />
            <h2 className="mt-4 text-3xl md:text-4xl font-semibold tracking-tight">
              Spend the time on the music, not the upload form.
            </h2>
            <p className="mt-4 max-w-md mx-auto text-sm text-zinc-400">
              We're in early access. Sign up, connect your platforms, and start
              uploading in under five minutes.
            </p>
            <div className="mt-8">
              <Button size="lg" asChild>
                <Link to="/login">
                  Create your account
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className="relative z-10 border-t border-zinc-900/80 bg-zinc-950/50 backdrop-blur">
        <div className="mx-auto max-w-6xl px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-zinc-500">
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 items-center justify-center rounded bg-gradient-to-br from-zinc-200 to-zinc-400 text-zinc-950">
              <Disc3 className="h-3 w-3" />
            </div>
            <span>© {new Date().getFullYear()} Beatuploader</span>
          </div>
          <div className="flex items-center gap-5">
            <Link to="/privacy" className="hover:text-zinc-300 transition-colors">
              Privacy
            </Link>
            <Link to="/terms" className="hover:text-zinc-300 transition-colors">
              Terms
            </Link>
            <a
              href="mailto:hello@beatuploader.com"
              className="hover:text-zinc-300 transition-colors"
            >
              Contact
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

function BackgroundGlow() {
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-0 h-[600px] bg-[radial-gradient(ellipse_60%_50%_at_50%_0%,rgba(80,80,80,0.18),transparent_70%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-[400px] -z-0 h-[400px] bg-[radial-gradient(ellipse_50%_40%_at_50%_50%,rgba(60,60,60,0.10),transparent_70%)]" />
    </>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-500">
      {children}
    </span>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  body,
  delay,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
  delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, delay, ease: easeOut }}
      className="rounded-xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900/50 to-zinc-900/10 p-6 transition-colors hover:border-zinc-700/80"
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-md bg-zinc-900 border border-zinc-800">
        <Icon className="h-4 w-4 text-zinc-300" />
      </div>
      <h3 className="mt-4 text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-2 text-xs text-zinc-400 leading-relaxed">{body}</p>
    </motion.div>
  );
}

function Step({
  n,
  title,
  body,
}: {
  n: number;
  title: string;
  body: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.5, ease: easeOut }}
    >
      <div className="flex items-center gap-2 text-xs text-zinc-500">
        <span className="flex h-5 w-5 items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-[10px] font-medium text-zinc-300">
          {n}
        </span>
        <span className="uppercase tracking-widest text-[10px]">Step {n}</span>
      </div>
      <h3 className="mt-3 text-lg font-semibold tracking-tight">{title}</h3>
      <p className="mt-2 text-sm text-zinc-400 leading-relaxed">{body}</p>
    </motion.div>
  );
}
