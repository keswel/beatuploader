import { LegalLayout } from "./layout";

export function TermsPage() {
  return (
    <LegalLayout title="Terms of service" updated="2026-05-20">
      <p>
        By creating an account or using Beatuploader you agree to these terms.
        Read them carefully — they're short on purpose.
      </p>

      <h2>The service</h2>
      <p>
        Beatuploader lets you push beats to multiple distribution platforms
        (BeatStars, YouTube, etc.) from one dashboard. We're an independent
        product — not affiliated with, endorsed by, or partnered with any of
        those platforms.
      </p>

      <h2>Your account</h2>
      <ul>
        <li>
          You're responsible for keeping your password and connected platform
          credentials safe.
        </li>
        <li>
          You must be old enough to enter a binding contract in your
          jurisdiction (typically 13+, 18+ in some places).
        </li>
        <li>One account per person. Don't share accounts.</li>
      </ul>

      <h2>Your content</h2>
      <p>
        You own the audio, artwork, and metadata you upload. By uploading,
        you grant us a non-exclusive license to store, process, and transmit
        that content for the sole purpose of publishing it to the platforms
        you've connected. That's it — we don't claim any ownership.
      </p>
      <p>
        You promise that everything you upload is yours to upload (you wrote
        it, you cleared every sample, you own the cover art rights). You
        accept full responsibility for any infringement claims arising from
        your content.
      </p>

      <h2>Third-party platforms</h2>
      <p>
        When you connect a platform, you're also bound by that platform's
        terms (e.g.{" "}
        <a
          href="https://www.youtube.com/t/terms"
          target="_blank"
          rel="noreferrer"
        >
          YouTube
        </a>
        ,{" "}
        <a
          href="https://www.beatstars.com/terms"
          target="_blank"
          rel="noreferrer"
        >
          BeatStars
        </a>
        ). Their rules about content, monetization, takedowns, and account
        suspension apply to anything we publish on your behalf. If a platform
        bans your account, we can't get you back in.
      </p>

      <h2>What we don't promise</h2>
      <ul>
        <li>
          We don't promise uptime, that every upload will succeed, or that
          third-party platforms won't change their UI in a way that breaks an
          integration (especially BeatStars — see "headless" in our docs).
        </li>
        <li>
          We can suspend accounts that abuse the service (uploading content
          that triggers platform takedowns, attempting to compromise the
          system, automating to evade rate limits, etc.).
        </li>
      </ul>

      <h2>Liability</h2>
      <p>
        Beatuploader is provided "as is" without warranties. To the maximum
        extent allowed by law, our total liability for any claim arising from
        the service is limited to the amount you paid us in the 12 months
        before the claim — currently zero, since we don't charge yet. We're
        not liable for indirect, incidental, or consequential damages
        (lost revenue, lost listeners, etc.).
      </p>

      <h2>Cancellation</h2>
      <p>
        You can delete your account from{" "}
        <a href="/settings">Settings → Danger zone</a>. We can terminate
        access if you breach these terms; we'll try to give a heads-up unless
        the breach is serious enough that we can't.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms over time. Material changes will be flagged
        with a new "Last updated" date and, when significant, emailed to
        you. Continued use after a change means you accept the updated
        terms.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about these terms?{" "}
        <a href="mailto:hello@beatuploader.com">hello@beatuploader.com</a>.
      </p>
    </LegalLayout>
  );
}
