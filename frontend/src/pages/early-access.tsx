import { EarlyReleaseSignup } from "@/components/early-release-signup";
import { Collage, SiteFonts, SiteFooter, SiteHeader } from "@/components/site-chrome";

// /early-access: why to join the early-release list. The first 50 signups are
// founding members (Premium free for life; terms on /terms#founding-members).
// Same collage system as the landing page; styles in landing.css.

const PERKS = [
  {
    title: "One-click uploads from FL Studio",
    body: "Export a beat and Beatuploader notices. Confirm the title and price, click once, and it's up. No dragging files around.",
  },
  {
    title: "Automatic videos",
    body: "A YouTube video made from your beat and cover art, ready to post. No video editor needed.",
  },
  {
    title: "Everything Premium adds later",
    body: "Free for life covers new Premium features too. And what you tell us shapes what gets built next.",
  },
];

export function EarlyAccessPage() {
  return (
    <div className="landing">
      <SiteFonts />
      <SiteHeader>
        <a href="#signup">Sign up</a>
        <a href="/#download">Download</a>
      </SiteHeader>

      <main>
        <Collage preset="pale" className="ea-head">
          <div className="wrap">
            <h1>
              <span className="row"><span className="strip">Get in early.</span></span>
            </h1>
            <div className="paper ea-intro">
              <p>
                Uploading to BeatStars and YouTube is free, and always will
                be. Premium adds automation on top for a small fee. The{" "}
                <b>first 50 people</b> on the early-release list get Premium
                free for life.
              </p>
            </div>
          </div>
        </Collage>

        <Collage preset="haze" className="how">
          <div className="wrap">
            <h2><span className="strip">What Premium does</span></h2>
            <ol className="steps">
              {PERKS.map((p, i) => (
                <li key={p.title} className="paper">
                  <span className="step-n" aria-hidden>{i + 1}</span>
                  <b>{p.title}</b>
                  <span>{p.body}</span>
                </li>
              ))}
            </ol>
          </div>
        </Collage>

        <section className="local">
          <div className="wrap">
            <h2>How the first 50 works.</h2>
            <div className="cols">
              <div>
                <b>Signup order</b>
                <p>Spots go to the first 50 emails on the list. One per person.</p>
              </div>
              <div>
                <b>Free for life</b>
                <p>Premium stays free for you as long as Beatuploader offers it.</p>
              </div>
              <div>
                <b>Still being built</b>
                <p>Premium isn't out yet. We'll email you when it's ready.</p>
              </div>
            </div>
          </div>
        </section>

        <Collage preset="grass" className="final" id="signup">
          <div className="wrap">
            <EarlyReleaseSignup title="Join the list" />
          </div>
        </Collage>
      </main>

      <SiteFooter />
    </div>
  );
}
