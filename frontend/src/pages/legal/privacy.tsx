import { LegalLayout } from "./layout";

export function PrivacyPage() {
  return (
    <LegalLayout title="Privacy policy" updated="2026-10-02">
      <p>
        Beatuploader is a desktop app that runs on your own computer. It has
        no accounts and no servers of ours in the middle: your files, your
        logins and your upload history stay on your machine. This page
        explains exactly what that means. Questions:{" "}
        <a href="mailto:hello@beatuploader.app">hello@beatuploader.app</a>.
      </p>

      <h2>What we collect</h2>
      <p>
        Nothing. We don't run analytics, crash reporting or tracking in the
        app, and the app never sends your data to us.
      </p>

      <h2>What the app stores on your computer</h2>
      <p>
        Everything below lives in <code>%APPDATA%\Beatuploader</code> on your
        PC and never leaves it, except when the app sends it to a platform
        you connected (see the next section).
      </p>
      <ul>
        <li>
          <strong>Platform sign-ins.</strong> For YouTube, the access and
          refresh tokens Google issues when you click Connect. For BeatStars,
          the session tokens BeatStars issues when you sign in. Your BeatStars
          password is used only for that sign-in and is never stored. The
          tokens are encrypted, and the encryption key is kept in Windows
          Credential Manager, separately from the data it protects.
        </li>
        <li>
          <strong>Your uploads.</strong> Copies of the files you add (audio,
          stems, cover art) and the details you enter (title, BPM, key, tags,
          genre, price), plus the status of each upload.
        </li>
        <li>
          <strong>Logs.</strong> A local log file used to diagnose failed
          uploads. It can include error messages returned by BeatStars or
          YouTube.
        </li>
      </ul>

      <h2>Who the app talks to</h2>
      <ul>
        <li>
          <strong>BeatStars and YouTube</strong>, but only the ones you
          connect, and only to sign in and to publish what you choose to
          upload. Their own privacy policies apply to what you send them.
        </li>
        <li>
          <strong>GitHub</strong>, to check for app updates and download
          them. GitHub sees your IP address and the app version, like any
          download.
        </li>
        <li>
          <strong>Google Fonts</strong>, to load the app's typeface.
        </li>
      </ul>

      <h2>Google user data</h2>
      <p>
        Beatuploader requests two YouTube permissions:{" "}
        <code>youtube.upload</code>, to upload the videos you submit, and{" "}
        <code>youtube.readonly</code>, to show which channel you connected.
        Data received from Google APIs is stored only on your computer, is
        used only for those two purposes, and is never transferred to us or
        anyone else. Beatuploader's use and transfer of information received
        from Google APIs adheres to the{" "}
        <a
          href="https://developers.google.com/terms/api-services-user-data-policy"
          target="_blank"
          rel="noreferrer"
        >
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements.
      </p>

      <h2>Removing your data</h2>
      <ul>
        <li>
          <strong>Disconnect a platform</strong> in the app's Platforms page
          to delete its stored sign-in.
        </li>
        <li>
          <strong>Revoke YouTube access</strong> at any time from your{" "}
          <a
            href="https://myaccount.google.com/permissions"
            target="_blank"
            rel="noreferrer"
          >
            Google account permissions
          </a>
          .
        </li>
        <li>
          <strong>Remove everything</strong> by uninstalling the app, then
          deleting the <code>%APPDATA%\Beatuploader</code> folder and the
          "Beatuploader" entry in Windows Credential Manager.
        </li>
      </ul>

      <h2>This website</h2>
      <p>
        beatuploader.app has no analytics or cookies. It's hosted on Vercel,
        whose servers keep standard request logs (such as IP addresses) to
        operate the site.
      </p>

      <h2>Donations</h2>
      <p>
        If you choose to donate, the payment is handled by the payment
        provider you're sent to, under its own privacy policy. We receive
        only what that provider shares with us about the donation.
      </p>

      <h2>Changes</h2>
      <p>
        If this policy changes, we'll update it here and change the date at
        the top.
      </p>
    </LegalLayout>
  );
}
