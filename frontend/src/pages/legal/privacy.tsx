import { LegalLayout } from "./layout";

export function PrivacyPage() {
  return (
    <LegalLayout title="Privacy policy" updated="2026-05-20">
      <p>
        This page explains what Beatuploader collects, what it does with that
        information, and the choices you have. We try to keep this short and
        in plain language; if anything is unclear, email{" "}
        <a href="mailto:privacy@beatuploader.com">privacy@beatuploader.com</a>.
      </p>

      <h2>What we collect</h2>
      <ul>
        <li>
          <strong>Account info.</strong> Your email, chosen handle, and (if you
          set one) a bcrypt-hashed password. If you sign in with Google, we
          also store your Google subject ID so we can recognize you on return.
        </li>
        <li>
          <strong>Platform credentials.</strong> When you connect a third-party
          platform (YouTube via OAuth, BeatStars via login on your behalf), we
          store the tokens or session cookies the platform issues, encrypted at
          rest with a per-deployment key (Fernet/AES-128). For BeatStars
          specifically, your password is stored encrypted because BeatStars
          requires re-authentication when the session expires.
        </li>
        <li>
          <strong>Uploads.</strong> The audio files, cover art, and metadata
          you upload, kept on our storage so we can push them to your
          connected platforms.
        </li>
        <li>
          <strong>Operational logs.</strong> Standard server logs (request
          path, status code, timestamps, client IP) and diagnostic HTML/screen
          captures when a BeatStars upload fails. Diagnostic captures are
          deleted automatically after 7 days.
        </li>
      </ul>

      <h2>What we don't collect</h2>
      <ul>
        <li>
          We don't run analytics or advertising trackers. No third-party
          fingerprinting scripts.
        </li>
        <li>
          We don't read or store your YouTube watch history or any data
          unrelated to the upload scopes you granted.
        </li>
      </ul>

      <h2>How we use it</h2>
      <p>
        Solely to make the product work: authenticating you, pushing your
        beats to platforms you connected, and showing you the status of those
        uploads. We do not sell your data. We do not share it with third
        parties except the platforms you've explicitly connected (YouTube,
        BeatStars, etc.), and only the data needed to publish on your behalf.
      </p>

      <h2>Google user data</h2>
      <p>
        Beatuploader's use and transfer of information received from Google
        APIs adheres to the{" "}
        <a
          href="https://developers.google.com/terms/api-services-user-data-policy"
          target="_blank"
          rel="noreferrer"
        >
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements. The YouTube scopes we
        request (<code>youtube.upload</code>, <code>youtube.readonly</code>)
        are used only to upload videos you submit and to display your channel
        name.
      </p>

      <h2>Data retention</h2>
      <ul>
        <li>Account and upload data: as long as your account exists.</li>
        <li>
          Diagnostic captures: 7 days, after which they're deleted from disk.
        </li>
        <li>
          When you delete your account (Settings → Danger zone), everything
          tied to it — uploads, platform connections, encrypted tokens — is
          removed.
        </li>
      </ul>

      <h2>Security</h2>
      <p>
        Passwords are bcrypt-hashed. Platform tokens and BeatStars session
        cookies are encrypted at rest. All traffic in production is over
        HTTPS. Internal access is restricted to a small number of operators.
        No system is perfect, but we treat your data the way we'd want ours
        treated.
      </p>

      <h2>Your rights</h2>
      <p>
        You can export or delete your data at any time from{" "}
        <a href="/settings">Settings</a>. If you'd like a copy of everything
        we hold about you, email{" "}
        <a href="mailto:privacy@beatuploader.com">privacy@beatuploader.com</a>{" "}
        and we'll send it within 30 days.
      </p>

      <h2>Changes to this policy</h2>
      <p>
        If we make material changes we'll update the "Last updated" date at
        the top and, for substantive changes, notify you by email. Continued
        use of Beatuploader after a change means you accept the updated
        policy.
      </p>
    </LegalLayout>
  );
}
