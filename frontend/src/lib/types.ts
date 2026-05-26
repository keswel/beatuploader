// Mirrors backend Pydantic schemas. Keep in sync with app/schemas/*.

export type PlatformProvider =
  | "beatstars"
  | "youtube"
  | "soundcloud"
  | "spotify"
  | "audiomack"
  | "bandcamp";

export type PlatformStatus = "connected" | "disconnected" | "error";

export type UploadStatus = "queued" | "uploading" | "done" | "failed";

export type BeatPlatformStatus = "live" | "uploading" | "failed" | "none";

export interface User {
  id: number;
  email: string;
  handle: string;
  plan: string;
  email_verified_at: string | null;
  youtube_description_template: string | null;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  user: User;
}

export interface PlatformOut {
  id: number;
  provider: PlatformProvider;
  status: PlatformStatus;
  account_label: string | null;
  connected_at: string | null;
  last_error: string | null;
  // False when the operator hasn't provisioned this connector's credentials
  // yet — the UI shows it as "Coming soon" instead of a Connect button.
  // Optional: an older/lagging backend may omit it, which we treat as available.
  configured?: boolean;
}

export interface UploadOut {
  id: number;
  filename: string;
  size_bytes: number;
  progress: number;
  status: UploadStatus;
  targets: Record<string, { status: UploadStatus; progress: number }>;
  error: string | null;
  created_at: string;
  updated_at: string;
  has_artwork: boolean;
}

export type LicenseType =
  | "AUTO"
  | "EXCLUSIVE"
  | "PREMIUM_PLUS"
  | "PREMIUM"
  | "UNLIMITED";

export interface UploadCreate {
  filename: string;
  size_bytes: number;
  targets: PlatformProvider[];
  title?: string;
  tags?: string[];
  bpm?: number;
  music_key?: string;
  price_cents?: number;
  license_type?: LicenseType;
  genre?: string;
  description?: string;  // per-upload YouTube description override
}

export interface UploadFiles {
  // tagged (MP3) is the required file — Basic license needs it,
  // and BeatStars can't publish without an MP3 preview
  tagged: File;
  master?: File;
  stems?: File;
  artwork?: File;  // cover art (PNG/JPG)
  video?: File;    // MP4/MOV/WEBM, YouTube only
}

export interface BeatOut {
  id: number;
  title: string;
  bpm: number | null;
  music_key: string | null;
  tags: string[];
  price_cents: number | null;
  plays: number;
  platform_statuses: Partial<Record<PlatformProvider, BeatPlatformStatus>>;
  released_at: string | null;
  created_at: string;
}

export interface ApiError {
  detail: string;
  status: number;
}
