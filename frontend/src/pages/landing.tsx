import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Collage, SiteFonts, SiteFooter, SiteHeader } from "@/components/site-chrome";
import { DONATE_URL, DOWNLOAD_URL } from "@/lib/target";

// Public page for beatuploader.app: what it does, download, donate.
// Cut-paper collage over generated skies; styles live in landing.css.

// Off until the installer is ready to hand out: the buttons read "Coming soon".
const DOWNLOAD_ENABLED = false;

const STEPS = [
  { title: "Add your files", body: "The tagged MP3, plus the WAV, stems and cover art if you have them." },
  { title: "Check the details", body: "Licenses are picked from the files you added. Set a price if you want one." },
  { title: "Upload", body: "It publishes to BeatStars and posts to YouTube at the same time." },
];

const FACTS = [
  { title: "No account", body: "Connect BeatStars and YouTube once, inside the app." },
  { title: "No saved password", body: "Only an encrypted session is kept, on your PC." },
  { title: "Updates itself", body: "New versions install the next time you open it." },
];

export function LandingPage() {
  const [downloadOpen, setDownloadOpen] = useState(false);
  // The link itself starts the download; the dialog just opens alongside it.
  const onDownload = () => setDownloadOpen(true);

  return (
    <div className="landing">
      <SiteFonts />
      <SiteHeader>
        <a href="#how">How it works</a>
        <a href="#download">Download</a>
      </SiteHeader>

      <main>
        <Collage preset="hero" className="hero">
          <div className="wrap">
            <div className="paper intro">
              <p>
                Beatuploader is a free Windows app for producers. Add a beat's
                files once and it uploads to BeatStars and YouTube at the same
                time.
              </p>
              <div className="cta-row">
                <DownloadButton onClick={onDownload} />
                <span className="meta">Free, for Windows 10 and 11</span>
              </div>
            </div>

            <div className="fine w98" role="note" aria-label="About your data">
              <div className="w98-title">
                <span>Your data</span>
                <span className="w98-btns" aria-hidden>
                  <span className="w98-bevel">?</span>
                  <span className="w98-bevel">✕</span>
                </span>
              </div>
              <div className="w98-body">
                <span className="w98-icon" aria-hidden>i</span>
                <div>
                  <p>Everything runs on your own computer. There's no account to make.</p>
                  <p>
                    Your BeatStars and YouTube logins are kept in Windows
                    Credential Manager and are never sent to us.
                  </p>
                </div>
              </div>
              <div className="w98-actions" aria-hidden>
                <span className="w98-btn w98-bevel w98-default">OK</span>
              </div>
            </div>

            <h1>
              <span className="row"><span className="strip">Upload once.</span></span>
              <span className="row"><span className="strip">Post everywhere.</span></span>
            </h1>
          </div>
        </Collage>

        <Collage preset="pale" className="app-sec">
          <div className="wrap">
            <div className="paper app-note">
              <h2>This is the whole app</h2>
              <p>One screen. A recorded walkthrough will go here soon.</p>
            </div>
            <AppPreview />
          </div>
        </Collage>

        <Collage preset="haze" className="how" id="how">
          <div className="wrap">
            <h2><span className="strip">How it works</span></h2>
            <ol className="steps">
              {STEPS.map((s, i) => (
                <li key={s.title} className="paper">
                  <span className="step-n" aria-hidden>{i + 1}</span>
                  <b>{s.title}</b>
                  <span>{s.body}</span>
                </li>
              ))}
            </ol>
          </div>
        </Collage>

        <section className="local">
          <div className="wrap">
            <h2>Your logins stay on your computer.</h2>
            <div className="cols">
              {FACTS.map((f) => (
                <div key={f.title}>
                  <b>{f.title}</b>
                  <p>{f.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <Collage preset="grass" className="final" id="download">
          <div className="wrap">
            <div className="paper">
              <h2>Get Beatuploader</h2>
              <div className="cta-row">
                <DownloadButton onClick={onDownload} />
                <span className="meta">Free, for Windows 10 and 11</span>
              </div>
              {DOWNLOAD_ENABLED && (
                <details>
                  <summary>Windows says "Windows protected your PC"</summary>
                  <SmartScreenHelp />
                </details>
              )}
              {DONATE_URL && (
                <p className="donate">
                  Beatuploader is free. If it saves you time,{" "}
                  <a href={DONATE_URL} target="_blank" rel="noopener noreferrer">
                    you can donate here
                  </a>
                  .
                </p>
              )}
            </div>
          </div>
        </Collage>
      </main>

      <SiteFooter />

      <DownloadStartedDialog open={downloadOpen} onOpenChange={setDownloadOpen} />
    </div>
  );
}

function DownloadButton({ onClick }: { onClick: () => void }) {
  if (!DOWNLOAD_ENABLED) {
    return (
      <button type="button" className="btn" disabled>
        Coming soon
      </button>
    );
  }
  return (
    <a className="btn" href={DOWNLOAD_URL} onClick={onClick}>
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" aria-hidden>
        <path d="M10 3v10M5.5 8.5 10 13l4.5-4.5M4 16.5h12" />
      </svg>
      Download for Windows
    </a>
  );
}

function SmartScreenHelp() {
  return (
    <p>
      The installer isn't code-signed yet. Click <em>More info</em>, then{" "}
      <em>Run anyway</em>. You only need to do this once. Updates install
      without it.
    </p>
  );
}

/** Shown when a download starts: install help, plus one quiet donation ask. */
function DownloadStartedDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dl-overlay" />
        <Dialog.Content className="dl-dialog w98">
          <div className="w98-title">
            <Dialog.Title asChild>
              <span>Download started</span>
            </Dialog.Title>
            <span className="w98-btns">
              <Dialog.Close className="w98-bevel" aria-label="Close">✕</Dialog.Close>
            </span>
          </div>
          <div className="w98-body">
            <span className="w98-icon" aria-hidden>i</span>
            <Dialog.Description asChild>
              <div>
                <p>
                  Beatuploader-setup.exe is downloading. Open it when it's done
                  to install. If it didn't start,{" "}
                  <a className="w98-link" href={DOWNLOAD_URL}>download it again</a>.
                </p>
                <p>
                  If Windows says "Windows protected your PC", click More info,
                  then Run anyway.
                </p>
                {DONATE_URL && (
                  <p>
                    Beatuploader is free and has no ads. If it saves you time,
                    a small donation helps keep it going.
                  </p>
                )}
              </div>
            </Dialog.Description>
          </div>
          <div className="w98-actions">
            {DONATE_URL && (
              <a
                className="w98-btn w98-bevel"
                href={DONATE_URL}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => onOpenChange(false)}
              >
                Donate
              </a>
            )}
            {/* Closing is the default action, so the ask never gets in the way. */}
            <Dialog.Close className="w98-btn w98-bevel w98-default">
              {DONATE_URL ? "Maybe later" : "OK"}
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Static mock of the upload screen, until the recorded walkthrough exists. */
function AppPreview() {
  return (
    <div
      className="window"
      role="img"
      aria-label="The Beatuploader upload screen with four files added; BeatStars is published and YouTube is at 64 percent"
    >
      <div className="titlebar">
        <span>Beatuploader</span>
        <span className="wc"><span>–</span><span>▢</span><span>✕</span></span>
      </div>
      <div className="pane">
        <h3>New upload</h3>
        <div className="files">
          <div className="file"><b>night_drive_tagged.mp3</b><small>Tagged MP3, 7.4 MB</small></div>
          <div className="file"><b>night_drive_master.wav</b><small>Master WAV, 42 MB</small></div>
          <div className="file"><b>night_drive_stems.zip</b><small>Stems, 318 MB</small></div>
          <div className="file"><b>cover.png</b><small>Artwork, 1.2 MB</small></div>
        </div>
        <div className="fields">
          <div className="field"><small>Title</small>Night Drive</div>
          <div className="field"><small>BPM</small>140</div>
          <div className="field"><small>Key</small>F minor</div>
        </div>
        <div className="chips">
          <span className="chip on">Premium</span>
          <span className="chip on">Unlimited</span>
          <span className="chip on">Exclusive</span>
          <span className="chip">Basic</span>
        </div>
        <div className="targets">
          <div className="trow">
            <span>BeatStars</span>
            <span className="bar"><i style={{ width: "100%" }} /></span>
            <span className="st live">Published</span>
          </div>
          <div className="trow">
            <span>YouTube</span>
            <span className="bar"><i style={{ width: "64%" }} /></span>
            <span className="st">64%</span>
          </div>
        </div>
      </div>
    </div>
  );
}
