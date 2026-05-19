import { useCallback, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  UploadCloud,
  X,
  Music2,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Plus,
  FileAudio,
  FileArchive,
  ImageIcon,
  RotateCcw,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { PageHeader } from "@/components/page-header";
import { AuthedImage } from "@/components/authed-image";
import { cn, formatBytes } from "@/lib/utils";
import { api, ApiError } from "@/lib/api";
import type {
  LicenseType,
  PlatformProvider,
  UploadOut,
  UploadStatus,
} from "@/lib/types";

type FileRole = "master" | "tagged" | "stems" | "artwork";

interface PendingFiles {
  master: File | null;
  tagged: File | null;
  stems: File | null;
  artwork: File | null;
}

interface Metadata {
  title: string;
  tags: string;
  bpm: string;
  music_key: string;
  price: string;
  license_type: LicenseType;
  genre: string;
}

const emptyFiles: PendingFiles = {
  master: null,
  tagged: null,
  stems: null,
  artwork: null,
};
const emptyMeta: Metadata = {
  title: "",
  tags: "",
  bpm: "",
  music_key: "",
  price: "",
  license_type: "AUTO",
  genre: "",
};

// BeatStars's most common genres. Their input is autocomplete-only — typing
// something not in their list silently fails to add a chip. Stay on the safe side.
const COMMON_GENRES = [
  "Hip Hop",
  "Trap",
  "R&B",
  "Drill",
  "Pop",
  "Afrobeat",
  "Dancehall",
  "House",
  "EDM",
  "Reggaeton",
  "Latin",
  "Rock",
  "Country",
  "Lo-fi",
  "Pluggnb",
  "Phonk",
  "Alternative Hip Hop",
  "Soul",
  "Funk",
  "Jazz",
];

function classify(file: File): FileRole | null {
  const name = file.name.toLowerCase();
  if (name.endsWith(".wav") || name.endsWith(".wave") || name.endsWith(".flac")) {
    return "master";
  }
  if (name.endsWith(".mp3")) return "tagged";
  if (name.endsWith(".zip") || name.endsWith(".rar")) return "stems";
  if (
    name.endsWith(".png") ||
    name.endsWith(".jpg") ||
    name.endsWith(".jpeg") ||
    name.endsWith(".webp")
  ) {
    return "artwork";
  }
  return null;
}

const LICENSE_OPTIONS: { value: LicenseType; label: string; hint: string }[] = [
  {
    value: "AUTO",
    label: "Auto (all applicable)",
    hint: "Enables every license tier the uploaded files satisfy",
  },
  { value: "EXCLUSIVE", label: "Exclusive only", hint: "Needs WAV + MP3 + stems" },
  { value: "PREMIUM_PLUS", label: "Premium Plus only", hint: "Needs WAV + stems" },
  { value: "PREMIUM", label: "Premium only", hint: "Needs WAV" },
  { value: "UNLIMITED", label: "Unlimited only", hint: "Needs WAV + stems" },
];

export function UploadPage() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  const [files, setFiles] = useState<PendingFiles>(emptyFiles);
  const [dragOver, setDragOver] = useState(false);
  const [meta, setMeta] = useState<Metadata>(emptyMeta);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [unsorted, setUnsorted] = useState<string[]>([]);

  const { data: serverJobs = [] } = useQuery({
    queryKey: ["uploads"],
    queryFn: api.uploads.list,
    refetchInterval: (q) => {
      const items = q.state.data as UploadOut[] | undefined;
      const active = items?.some(
        (j) => j.status === "queued" || j.status === "uploading",
      );
      return active ? 2000 : false;
    },
  });

  const { data: platforms = [] } = useQuery({
    queryKey: ["platforms"],
    queryFn: api.platforms.list,
  });

  const [selectedTargets, setSelectedTargets] = useState<PlatformProvider[]>([]);
  if (selectedTargets.length === 0 && platforms.length > 0) {
    const connected = platforms
      .filter((p) => p.status === "connected")
      .map((p) => p.provider);
    if (connected.length > 0) setSelectedTargets(connected);
  }

  const createUpload = useMutation({
    mutationFn: ({
      files,
      payload,
    }: {
      files: { tagged: File; master?: File; stems?: File; artwork?: File };
      payload: Parameters<typeof api.uploads.create>[1];
    }) => api.uploads.create(files, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["uploads"] }),
  });

  const deleteUpload = useMutation({
    mutationFn: api.uploads.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["uploads"] }),
  });

  const retryUpload = useMutation({
    mutationFn: api.uploads.retry,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["uploads"] }),
  });

  const addFiles = useCallback((dropped: FileList | File[]) => {
    setUnsorted([]);
    setFiles((prev) => {
      const next = { ...prev };
      const unknown: string[] = [];
      for (const f of Array.from(dropped)) {
        const role = classify(f);
        if (role) next[role] = f;
        else unknown.push(f.name);
      }
      if (unknown.length > 0) setUnsorted(unknown);
      return next;
    });
  }, []);

  const togglePlatform = (id: PlatformProvider) => {
    setSelectedTargets((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id],
    );
  };

  const clearRole = (role: FileRole) =>
    setFiles((prev) => ({ ...prev, [role]: null }));

  const startUpload = async () => {
    setSubmitError(null);
    if (!files.tagged || selectedTargets.length === 0) return;
    // Primary file for filename/size hints: master if present, else tagged
    const primary = files.master ?? files.tagged;
    try {
      await createUpload.mutateAsync({
        files: {
          master: files.master ?? undefined,
          tagged: files.tagged,
          stems: files.stems ?? undefined,
          artwork: files.artwork ?? undefined,
        },
        payload: {
          filename: primary.name,
          size_bytes: primary.size,
          targets: selectedTargets,
          title: meta.title || primary.name.replace(/\.[^.]+$/, ""),
          tags: meta.tags
            ? meta.tags
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean)
            : undefined,
          bpm: meta.bpm ? Number(meta.bpm) : undefined,
          music_key: meta.music_key || undefined,
          price_cents: meta.price
            ? Math.round(Number(meta.price) * 100)
            : undefined,
          license_type: meta.license_type,
          genre: meta.genre || undefined,
        },
      });
      setFiles(emptyFiles);
      setMeta(emptyMeta);
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.detail : "Upload failed");
    }
  };

  const totalBytes =
    (files.master?.size ?? 0) +
    (files.tagged?.size ?? 0) +
    (files.stems?.size ?? 0) +
    (files.artwork?.size ?? 0);
  const fileCount = [files.master, files.tagged, files.stems, files.artwork].filter(
    Boolean,
  ).length;

  // BeatStars requires at least one tag. If BeatStars is a target, gate submit on tags.
  const parsedTags = meta.tags
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  const beatstarsSelected = selectedTargets.includes("beatstars");
  const tagsRequired = beatstarsSelected;
  const tagsMissing = tagsRequired && parsedTags.length === 0;

  return (
    <>
      <PageHeader
        title="Upload"
        description="Drop files, set metadata, push to every connected platform."
        actions={
          <Button
            size="sm"
            disabled={
              !files.tagged ||
              selectedTargets.length === 0 ||
              tagsMissing ||
              createUpload.isPending
            }
            onClick={startUpload}
          >
            {createUpload.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <UploadCloud className="h-4 w-4" />
            )}
            Start upload
          </Button>
        }
      />

      <div className="grid gap-4 grid-cols-1 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <motion.div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
            }}
            onClick={() => inputRef.current?.click()}
            animate={{
              scale: dragOver ? 1.01 : 1,
              borderColor: dragOver ? "rgb(113 113 122)" : "rgb(39 39 42)",
            }}
            transition={{ duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
            className={cn(
              "group relative cursor-pointer rounded-xl border border-dashed transition-colors overflow-hidden",
              dragOver
                ? "bg-zinc-900/60"
                : "bg-gradient-to-b from-zinc-900/40 to-zinc-900/10 hover:bg-zinc-900/40",
            )}
          >
            {dragOver && (
              <div className="absolute inset-0 shimmer pointer-events-none" />
            )}
            <div className="relative flex flex-col items-center justify-center px-6 py-12 text-center">
              <div className="h-12 w-12 rounded-full bg-gradient-to-br from-zinc-800 to-zinc-900 ring-1 ring-zinc-700/50 flex items-center justify-center mb-4 shadow-[0_0_30px_-6px_rgba(255,255,255,0.1)]">
                <UploadCloud className="h-5 w-5 text-zinc-300" />
              </div>
              <div className="text-sm font-medium text-zinc-100">
                Drop your files here
              </div>
              <div className="mt-1 text-xs text-zinc-500">
                We'll sort them: <span className="font-mono">.wav</span> → master,{" "}
                <span className="font-mono">.mp3</span> → tagged,{" "}
                <span className="font-mono">.zip/.rar</span> → stems,{" "}
                <span className="font-mono">.png/.jpg</span> → artwork
              </div>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept="audio/*,image/*,.zip,.rar"
                className="hidden"
                onChange={(e) => e.target.files && addFiles(e.target.files)}
              />
            </div>
          </motion.div>

          {unsorted.length > 0 && (
            <div className="text-xs text-amber-300 bg-amber-950/30 border border-amber-900/50 rounded-md px-3 py-2">
              Couldn't categorize: {unsorted.join(", ")} — unsupported extension.
            </div>
          )}

          {submitError && (
            <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
              {submitError}
            </div>
          )}

          <Card>
            <CardContent className="p-0">
              <div className="px-5 py-3.5 border-b border-zinc-800/60 flex items-center justify-between">
                <div className="text-sm font-medium">Files</div>
                <div className="text-xs text-zinc-500 tabular-nums">
                  {fileCount} / 4 · {formatBytes(totalBytes)}
                </div>
              </div>
              <div className="divide-y divide-zinc-800/60">
                <FileSlot
                  role="tagged"
                  label="MP3 preview"
                  hint="Required. Basic license uses this."
                  required
                  file={files.tagged}
                  onClear={() => clearRole("tagged")}
                />
                <FileSlot
                  role="master"
                  label="Master (WAV/FLAC)"
                  hint="Optional. Required for Premium and Unlimited licenses."
                  file={files.master}
                  onClear={() => clearRole("master")}
                />
                <FileSlot
                  role="stems"
                  label="Stems"
                  hint="Optional. ZIP/RAR. Required for Exclusive."
                  file={files.stems}
                  onClear={() => clearRole("stems")}
                />
                <FileSlot
                  role="artwork"
                  label="Cover art"
                  hint="Optional. PNG/JPG/WebP. Recommended ≥1000×1000px."
                  file={files.artwork}
                  onClear={() => clearRole("artwork")}
                />
              </div>
            </CardContent>
          </Card>

          {serverJobs.length > 0 && (
            <Card>
              <CardContent className="p-0">
                <div className="px-5 py-3.5 border-b border-zinc-800/60 flex items-center justify-between">
                  <div className="text-sm font-medium">Recent uploads</div>
                  <div className="text-xs text-zinc-500 tabular-nums">
                    {serverJobs.length}
                  </div>
                </div>
                <div className="divide-y divide-zinc-800/60">
                  <AnimatePresence initial={false}>
                    {serverJobs.slice(0, 10).map((job) => (
                      <ServerJobRow
                        key={job.id}
                        job={job}
                        onRemove={() => deleteUpload.mutate(job.id)}
                        onRetry={() => retryUpload.mutate(job.id)}
                        retrying={
                          retryUpload.isPending &&
                          retryUpload.variables === job.id
                        }
                      />
                    ))}
                  </AnimatePresence>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardContent className="p-5 space-y-4">
              <div>
                <div className="text-sm font-medium mb-3">Destinations</div>
                <div className="space-y-2">
                  {platforms.length === 0 && (
                    <div className="text-xs text-zinc-500 py-2">
                      Loading platforms...
                    </div>
                  )}
                  {platforms.map((p) => {
                    const connected = p.status === "connected";
                    const checked = selectedTargets.includes(p.provider);
                    return (
                      <label
                        key={p.provider}
                        className={cn(
                          "flex items-center justify-between gap-3 rounded-md border px-3 py-2.5 cursor-pointer transition-colors",
                          checked && connected
                            ? "border-zinc-700 bg-zinc-900/60"
                            : "border-zinc-800/60 bg-zinc-900/20 hover:bg-zinc-900/40",
                          !connected && "opacity-50 cursor-not-allowed",
                        )}
                      >
                        <div className="flex items-center gap-3">
                          <div
                            className={cn(
                              "h-4 w-4 rounded border flex items-center justify-center transition-colors",
                              checked && connected
                                ? "border-zinc-300 bg-zinc-100"
                                : "border-zinc-700 bg-transparent",
                            )}
                          >
                            {checked && connected && (
                              <CheckCircle2 className="h-3 w-3 text-zinc-950" />
                            )}
                          </div>
                          <span className="text-sm capitalize">{p.provider}</span>
                        </div>
                        {!connected && (
                          <Badge variant="outline" className="text-[10px]">
                            Not connected
                          </Badge>
                        )}
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!connected}
                          onChange={() => togglePlatform(p.provider)}
                          className="sr-only"
                        />
                      </label>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 space-y-4">
              <div className="text-sm font-medium">Metadata</div>
              <div className="space-y-3">
                <Field label="Title">
                  <Input
                    placeholder="Untitled beat"
                    value={meta.title}
                    onChange={(e) => setMeta({ ...meta, title: e.target.value })}
                  />
                </Field>
                <Field
                  label={
                    tagsRequired ? "Tags (required for BeatStars)" : "Tags"
                  }
                >
                  <Input
                    placeholder="trap, dark, 808"
                    value={meta.tags}
                    onChange={(e) => setMeta({ ...meta, tags: e.target.value })}
                    className={
                      tagsMissing ? "border-amber-900/60 focus:border-amber-700" : ""
                    }
                  />
                  {tagsMissing && (
                    <div className="text-[10px] text-amber-300 pt-1">
                      BeatStars requires at least one tag
                    </div>
                  )}
                </Field>
                <Field label="Genre (optional)">
                  <Input
                    list="bs-genres"
                    placeholder="Hip Hop"
                    value={meta.genre}
                    onChange={(e) => setMeta({ ...meta, genre: e.target.value })}
                  />
                  <datalist id="bs-genres">
                    {COMMON_GENRES.map((g) => (
                      <option key={g} value={g} />
                    ))}
                  </datalist>
                  <div className="text-[10px] text-zinc-600 pt-1">
                    Leave blank to keep whatever genre BeatStars used last time.
                  </div>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="BPM">
                    <Input
                      type="number"
                      placeholder="140"
                      value={meta.bpm}
                      onChange={(e) => setMeta({ ...meta, bpm: e.target.value })}
                    />
                  </Field>
                  <Field label="Key">
                    <Input
                      placeholder="C# min"
                      value={meta.music_key}
                      onChange={(e) =>
                        setMeta({ ...meta, music_key: e.target.value })
                      }
                    />
                  </Field>
                </div>
                <Field label="Price (USD)">
                  <Input
                    type="number"
                    placeholder="29.99"
                    value={meta.price}
                    onChange={(e) => setMeta({ ...meta, price: e.target.value })}
                  />
                </Field>
                <Field label="License">
                  <select
                    value={meta.license_type}
                    onChange={(e) =>
                      setMeta({
                        ...meta,
                        license_type: e.target.value as LicenseType,
                      })
                    }
                    className="flex h-9 w-full rounded-md border border-zinc-800 bg-zinc-900/50 px-3 py-1 text-sm text-zinc-100 shadow-sm focus:outline-none focus:ring-1 focus:ring-zinc-600 focus:border-zinc-700"
                  >
                    {LICENSE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <div className="text-[10px] text-zinc-600 pt-1">
                    {LICENSE_OPTIONS.find((o) => o.value === meta.license_type)
                      ?.hint}
                  </div>
                </Field>
              </div>
              <Button variant="outline" size="sm" className="w-full">
                <Plus className="h-3.5 w-3.5" />
                Save as preset
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-zinc-400">{label}</label>
      {children}
    </div>
  );
}

interface FileSlotProps {
  role: FileRole;
  label: string;
  hint: string;
  required?: boolean;
  file: File | null;
  onClear: () => void;
}

function FileSlot({ role, label, hint, required, file, onClear }: FileSlotProps) {
  const Icon =
    role === "stems"
      ? FileArchive
      : role === "artwork"
        ? ImageIcon
        : FileAudio;
  return (
    <div className="flex items-center gap-4 px-5 py-3.5">
      <div
        className={cn(
          "h-9 w-9 rounded-md ring-1 flex items-center justify-center shrink-0 transition-colors",
          file
            ? "bg-gradient-to-br from-zinc-700 to-zinc-900 ring-zinc-700"
            : "bg-zinc-900/40 ring-zinc-800",
        )}
      >
        <Icon
          className={cn(
            "h-4 w-4 transition-colors",
            file ? "text-zinc-200" : "text-zinc-600",
          )}
        />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{label}</span>
          {required && !file && (
            <Badge variant="outline" className="text-[9px]">
              Required
            </Badge>
          )}
        </div>
        {file ? (
          <div className="mt-0.5 flex items-center gap-2 text-xs text-zinc-500">
            <span className="truncate">{file.name}</span>
            <span className="shrink-0">· {formatBytes(file.size)}</span>
          </div>
        ) : (
          <div className="mt-0.5 text-xs text-zinc-500">{hint}</div>
        )}
      </div>
      {file && (
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClear}>
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

function ServerJobRow({
  job,
  onRemove,
  onRetry,
  retrying,
}: {
  job: UploadOut;
  onRemove: () => void;
  onRetry: () => void;
  retrying: boolean;
}) {
  const statusBadge = {
    queued: <Badge variant="outline">Queued</Badge>,
    uploading: (
      <Badge variant="default" className="gap-1">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> Uploading
      </Badge>
    ),
    done: (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-2.5 w-2.5" /> Done
      </Badge>
    ),
    failed: (
      <Badge variant="destructive" className="gap-1">
        <AlertCircle className="h-2.5 w-2.5" /> Failed
      </Badge>
    ),
  }[job.status as UploadStatus];

  return (
    <motion.div
      layout
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
      className="flex items-center gap-4 px-5 py-3.5 overflow-hidden"
    >
      <div className="h-9 w-9 rounded-md bg-gradient-to-br from-zinc-800 to-zinc-900 ring-1 ring-zinc-800 flex items-center justify-center shrink-0 overflow-hidden">
        <AuthedImage
          src={job.has_artwork ? `/uploads/${job.id}/artwork` : null}
          alt={job.filename}
          className="h-full w-full object-cover"
          fallback={<Music2 className="h-4 w-4 text-zinc-500" />}
        />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-medium truncate">{job.filename}</div>
          <div className="text-xs text-zinc-500 tabular-nums shrink-0">
            {formatBytes(job.size_bytes)}
          </div>
        </div>
        {job.status === "uploading" && (
          <div className="mt-2 flex items-center gap-3">
            <Progress value={job.progress} className="flex-1" />
            <div className="text-xs text-zinc-500 tabular-nums w-9 text-right">
              {job.progress}%
            </div>
          </div>
        )}
        {job.error && (
          <div className="mt-1 text-xs text-red-400 truncate">{job.error}</div>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {statusBadge}
        {(job.status === "failed" || job.status === "done") && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={onRetry}
            disabled={retrying}
            title="Retry with the same files and metadata"
          >
            {retrying ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" />
            )}
          </Button>
        )}
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onRemove}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </motion.div>
  );
}
