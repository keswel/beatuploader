import { LegalLayout } from "./layout";

export function TermsPage() {
  return (
    <LegalLayout title="Terms of use" updated="2026-10-06">
      <p>
        These terms cover the Beatuploader desktop app and this website. By
        installing or using the app, you agree to them.
      </p>

      <h2>The app</h2>
      <p>
        Beatuploader is software that runs on your computer and uploads
        your beats to platforms you connect, such as BeatStars and YouTube.
        Uploading to those platforms is free. The core app's source code is available under the{" "}
        <a
          href="https://github.com/keswel/beatuploader/blob/main/LICENSE"
          target="_blank"
          rel="noreferrer"
        >
          MIT License
        </a>
        . Beatuploader is independent and isn't affiliated with, endorsed by
        or partnered with BeatStars, YouTube or Google.
      </p>

      <h2>Your content</h2>
      <p>
        You own what you upload. The app only moves it from your computer to
        the platforms you choose. You're responsible for having the rights to
        everything you upload, including samples, vocals and cover art.
      </p>

      <h2>Platforms you connect</h2>
      <p>
        When you connect a platform, its own terms apply to your account and
        to everything published there (for example{" "}
        <a href="https://www.youtube.com/t/terms" target="_blank" rel="noreferrer">
          YouTube's
        </a>{" "}
        and{" "}
        <a href="https://www.beatstars.com/terms" target="_blank" rel="noreferrer">
          BeatStars'
        </a>
        ). BeatStars has no public API, so Beatuploader signs in and uploads
        the same way the BeatStars website does. BeatStars could change how
        that works, or object to it, at any time; if it affects your
        account, that's between you and BeatStars.
      </p>

      <h2>No warranty</h2>
      <p>
        Beatuploader is provided "as is", without warranties of any kind. We
        don't promise that every upload will succeed or that integrations
        will keep working when platforms change. Check that your releases
        published the way you intended.
      </p>

      <h2>Liability</h2>
      <p>
        To the maximum extent the law allows, we aren't liable for any
        damages arising from using Beatuploader, including lost sales, lost
        data, or actions a platform takes on your account.
      </p>

      <h2 id="founding-members">Premium and founding members</h2>
      <p>
        Some features, such as automatic videos and one-click uploads from FL
        Studio, will be part of a paid Premium tier. Premium isn't available
        yet. Uploading to the platforms you connect stays free.
      </p>
      <p>
        The first 50 people to join the early-release list on this website
        are founding members. Founding members get Premium free for as long
        as Beatuploader offers Premium, including Premium features added
        later. Spots go in the order signups were received. Founding
        membership is one per person, is tied to the email address used to
        sign up, and can't be transferred or sold. We may decline signups
        that look automated or duplicated.
      </p>

      <h2>Donations</h2>
      <p>
        Donations are voluntary and non-refundable. They don't buy Premium,
        features, support or any other service.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms. The date at the top shows when they last
        changed, and continuing to use the app after a change means you
        accept the new terms.
      </p>

      <h2>Contact</h2>
      <p>
        <a href="mailto:hello@beatuploader.app">hello@beatuploader.app</a>
      </p>
    </LegalLayout>
  );
}
