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

export const DOWNLOAD_URL =
  import.meta.env.VITE_DOWNLOAD_URL ??
  "https://github.com/keswel/beatuploader/releases/latest";
