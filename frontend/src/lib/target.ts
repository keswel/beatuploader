/**
 * Which app this bundle is.
 *
 * - web     (`vite build`)              — beatuploader.app: landing, legal, download.
 * - desktop (`vite build --mode desktop`) — the installed app's UI, served by the
 *   local backend on 127.0.0.1. No accounts; the dashboard is the whole app.
 *
 * The hosted dashboard (login, accounts, hosted API) is still in the codebase
 * but not routed in either build.
 */
export const IS_DESKTOP = import.meta.env.MODE === "desktop";

// Fixed-name copy of the installer that desktop-release.yml attaches to every
// release, so this link never goes stale when the version changes.
export const DOWNLOAD_URL =
  import.meta.env.VITE_DOWNLOAD_URL ??
  "https://github.com/keswel/beatuploader/releases/latest/download/Beatuploader-setup.exe";

/** Donation page (Ko-fi etc.). Unset = the donate link is hidden. */
export const DONATE_URL = import.meta.env.VITE_DONATE_URL ?? "";
