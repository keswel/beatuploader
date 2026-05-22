import type {
  BeatOut,
  PlatformOut,
  PlatformProvider,
  Token,
  UploadCreate,
  UploadFiles,
  UploadOut,
  User,
} from "./types";

// Dev fallback matches start-backend.ps1 (port 8001). In prod, VITE_API_BASE
// MUST be set at build time on Vercel — otherwise the bundle hits localhost.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8001/api";
const TOKEN_KEY = "beatuploader.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

/** Called when any request returns 401 — wired by AuthProvider to clear token + redirect. */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

async function request<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, headers, ...rest } = init;
  const finalHeaders = new Headers(headers);
  const isFormData =
    typeof FormData !== "undefined" && init.body instanceof FormData;
  if (!finalHeaders.has("Content-Type") && init.body && !isFormData) {
    finalHeaders.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...rest, headers: finalHeaders });

  if (res.status === 401 && auth) {
    onUnauthorized?.();
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  auth: {
    register: (payload: { email: string; handle: string; password: string }) =>
      request<Token>("/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
        auth: false,
      }),
    login: (payload: { email: string; password: string }) =>
      request<Token>("/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
        auth: false,
      }),
    me: () => request<User>("/auth/me"),
    updateMe: (payload: {
      handle?: string;
      youtube_description_template?: string | null;
    }) =>
      request<User>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
    changePassword: (payload: {
      current_password?: string;
      new_password: string;
    }) =>
      request<void>("/auth/change-password", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    deleteMe: (confirm_handle: string) =>
      request<void>("/auth/me", {
        method: "DELETE",
        body: JSON.stringify({ confirm_handle }),
      }),
    googleStart: () =>
      request<{ authorize_url: string; state: string }>("/auth/google/start", {
        method: "POST",
        auth: false,
      }),
    forgotPassword: (email: string) =>
      request<{ status: string }>("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
        auth: false,
      }),
    resetPassword: (payload: { token: string; new_password: string }) =>
      request<void>("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify(payload),
        auth: false,
      }),
  },
  platforms: {
    list: () => request<PlatformOut[]>("/platforms"),
    connect: (provider: PlatformProvider) =>
      request<{ authorize_url: string; state: string }>(
        `/platforms/${provider}/connect`,
        { method: "POST" },
      ),
    disconnect: (provider: PlatformProvider) =>
      request<void>(`/platforms/${provider}`, { method: "DELETE" }),
    beatstarsCredentials: (payload: { username: string; password: string }) =>
      request<
        | { status: "connected"; account_label: string }
        | { status: "sms_required"; challenge_id: string; hint: string }
      >("/platforms/beatstars/credentials", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    beatstarsSms: (payload: { challenge_id: string; code: string }) =>
      request<{ status: "connected"; account_label: string }>(
        "/platforms/beatstars/sms",
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    beatstarsSmsCancel: (challenge_id: string) =>
      request<void>(`/platforms/beatstars/sms/${challenge_id}`, {
        method: "DELETE",
      }),
  },
  uploads: {
    list: () => request<UploadOut[]>("/uploads"),
    get: (id: number) => request<UploadOut>(`/uploads/${id}`),
    create: (files: UploadFiles, payload: UploadCreate) => {
      const form = new FormData();
      form.append("tagged", files.tagged);
      if (files.master) form.append("master", files.master);
      if (files.stems) form.append("stems", files.stems);
      if (files.artwork) form.append("artwork", files.artwork);
      if (files.video) form.append("video", files.video);
      form.append("metadata", JSON.stringify(payload));
      return request<UploadOut>("/uploads", {
        method: "POST",
        body: form,
      });
    },
    delete: (id: number) => request<void>(`/uploads/${id}`, { method: "DELETE" }),
    retry: (id: number) =>
      request<UploadOut>(`/uploads/${id}/retry`, { method: "POST" }),
  },
  library: {
    list: (params: { q?: string; limit?: number; offset?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.q) qs.set("q", params.q);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const suffix = qs.toString() ? `?${qs}` : "";
      return request<BeatOut[]>(`/library${suffix}`);
    },
  },
};
