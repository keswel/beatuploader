/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  /** Website "Download" link. Defaults to the latest GitHub release. */
  readonly VITE_DOWNLOAD_URL?: string;
  /** Website "Donate" link. Hidden when unset. */
  readonly VITE_DONATE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
