import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  Lock,
  Trash2,
  Loader2,
  AlertTriangle,
  Plug,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/page-header";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

export function SettingsPage() {
  const { user, logout } = useAuth();
  const qc = useQueryClient();
  const { data: platforms = [] } = useQuery({
    queryKey: ["platforms"],
    queryFn: api.platforms.list,
  });
  const connectedCount = platforms.filter((p) => p.status === "connected").length;

  return (
    <>
      <PageHeader
        title="Settings"
        description="Account, security, and integrations."
      />

      {!user ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
        </div>
      ) : (
        <div className="space-y-4 max-w-2xl">
          <AccountSection
            handle={user.handle}
            email={user.email}
            plan={user.plan}
            createdAt={user.created_at}
            onSaved={() => qc.invalidateQueries({ queryKey: ["auth", "me"] })}
          />
          <SecuritySection />
          <IntegrationsSection
            connectedCount={connectedCount}
            totalCount={platforms.length}
          />
          <DangerZone handle={user.handle} onDeleted={logout} />
        </div>
      )}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="mb-5">
          <div className="text-sm font-semibold">{title}</div>
          {description && (
            <div className="text-xs text-zinc-500 mt-0.5">{description}</div>
          )}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-zinc-400">{label}</label>
      {children}
      {hint && <div className="text-[10px] text-zinc-600 pt-0.5">{hint}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

function AccountSection({
  handle: initialHandle,
  email,
  plan,
  createdAt,
  onSaved,
}: {
  handle: string;
  email: string;
  plan: string;
  createdAt: string;
  onSaved: () => void;
}) {
  const [handle, setHandle] = useState(initialHandle);
  const [error, setError] = useState<string | null>(null);
  const dirty = handle !== initialHandle;

  const save = useMutation({
    mutationFn: () => api.auth.updateMe({ handle }),
    onSuccess: () => {
      setError(null);
      onSaved();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Couldn't save");
    },
  });

  return (
    <Section title="Account" description="Public details for your producer profile.">
      <div className="space-y-4">
        <Field label="Email" hint="Email changes aren't supported yet — reach out if you need one.">
          <Input value={email} readOnly disabled />
        </Field>
        <Field label="Handle" hint="Letters, numbers, _ . - only. Min 2 characters.">
          <Input
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            minLength={2}
            pattern="[a-zA-Z0-9_.\-]+"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Plan">
            <Input value={plan} readOnly disabled className="capitalize" />
          </Field>
          <Field label="Joined">
            <Input value={formatDate(createdAt)} readOnly disabled />
          </Field>
        </div>
        {error && (
          <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
            {error}
          </div>
        )}
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save changes
          </Button>
        </div>
      </div>
    </Section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

function SecuritySection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      api.auth.changePassword({
        current_password: current || undefined,
        new_password: next,
      }),
    onSuccess: () => {
      setSuccess(true);
      setCurrent("");
      setNext("");
      setConfirm("");
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Couldn't change password");
      setSuccess(false);
    },
  });

  const valid = next.length >= 8 && next === confirm;

  return (
    <Section title="Security" description="Change your password.">
      <div className="space-y-4">
        <Field label="Current password" hint="Leave blank if you signed up via Google.">
          <Input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="••••••••"
          />
        </Field>
        <Field label="New password" hint="Min 8 characters.">
          <Input
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="••••••••"
          />
        </Field>
        <Field label="Confirm new password">
          <Input
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="••••••••"
            className={
              confirm.length > 0 && next !== confirm
                ? "border-red-900/60 focus:border-red-700"
                : ""
            }
          />
        </Field>
        {error && (
          <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
            {error}
          </div>
        )}
        {success && (
          <div className="text-xs text-emerald-300 bg-emerald-950/30 border border-emerald-900/50 rounded-md px-3 py-2 flex items-center gap-2">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Password updated.
          </div>
        )}
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={!valid || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Lock className="h-3.5 w-3.5" />
            )}
            Update password
          </Button>
        </div>
      </div>
    </Section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

function IntegrationsSection({
  connectedCount,
  totalCount,
}: {
  connectedCount: number;
  totalCount: number;
}) {
  return (
    <Section title="Integrations" description="Manage your connected platforms.">
      <div className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800/60 bg-zinc-900/30 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-md bg-zinc-900 ring-1 ring-zinc-800 flex items-center justify-center">
            <Plug className="h-4 w-4 text-zinc-400" />
          </div>
          <div>
            <div className="text-sm font-medium">Connected platforms</div>
            <div className="text-xs text-zinc-500">
              {connectedCount} of {totalCount} active
            </div>
          </div>
        </div>
        <Button asChild variant="secondary" size="sm">
          <Link to="/platforms">Manage</Link>
        </Button>
      </div>
    </Section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

function DangerZone({
  handle,
  onDeleted,
}: {
  handle: string;
  onDeleted: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);

  const del = useMutation({
    mutationFn: () => api.auth.deleteMe(typed),
    onSuccess: () => {
      setOpen(false);
      onDeleted();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Couldn't delete");
    },
  });

  return (
    <>
      <Card className="border-red-900/30">
        <CardContent className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-red-300 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Danger zone
              </div>
              <div className="text-xs text-zinc-500 mt-1 max-w-md">
                Deleting your account is permanent. Your platform connections,
                uploads, library, and stored cookies are all removed.
              </div>
            </div>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => {
                setOpen(true);
                setTyped("");
                setError(null);
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete account
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete your account?</DialogTitle>
            <DialogDescription>
              Permanent. Type{" "}
              <span className="font-mono text-zinc-200">{handle}</span> below to
              confirm.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              autoFocus
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={handle}
            />
            {error && (
              <div className="text-xs text-red-400 bg-red-950/30 border border-red-900/50 rounded-md px-3 py-2">
                {error}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setOpen(false)}
                disabled={del.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={typed !== handle || del.isPending}
                onClick={() => del.mutate()}
              >
                {del.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                Delete forever
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

