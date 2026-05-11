import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { UserInfo } from "../api/auth";
import { formatCents, useTillSessions } from "../api/till";
import {
  type CreateUserRequest,
  type UserSummary,
  useCreateUser,
  useDeactivateUser,
  useResetUserPassword,
  useUsers,
} from "../api/users";

interface Props {
  user: UserInfo;
  onBack: () => void;
}

type Tab = "users" | "till";

export function SettingsScreen({ user, onBack }: Props) {
  const [tab, setTab] = useState<Tab>("users");
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <header className="flex items-center gap-4 bg-slate-900 px-6 py-3 text-sm">
        <button
          type="button"
          onClick={onBack}
          className="rounded-card border border-slate-700 bg-slate-800 px-3 py-1 font-mono text-xs font-semibold uppercase tracking-wider text-brand-cream hover:bg-slate-700"
        >
          ← Back
        </button>
        <span className="font-mono text-base font-bold uppercase tracking-wider text-brand-cream">
          Settings
        </span>
        <span className="ml-auto text-slate-300">{user.display_name}</span>
      </header>
      <nav className="flex items-end gap-1 border-b border-surface-border bg-surface px-6">
        <TabButton active={tab === "users"} onClick={() => setTab("users")}>
          Users
        </TabButton>
        <TabButton active={tab === "till"} onClick={() => setTab("till")}>
          Till Sessions
        </TabButton>
      </nav>
      <main className="flex-1 overflow-auto p-6">
        {tab === "users" ? <UsersTab currentUsername={user.username} /> : <TillSessionsTab />}
      </main>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`-mb-px rounded-t-card border border-b-0 px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider ${
        active
          ? "border-surface-border bg-surface text-ink"
          : "border-transparent text-ink-muted hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Users tab
// ---------------------------------------------------------------------------

function UsersTab({ currentUsername }: { currentUsername: string }) {
  const users = useUsers();
  const [showNew, setShowNew] = useState(false);
  const [resetUser, setResetUser] = useState<UserSummary | null>(null);
  const queryClient = useQueryClient();

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-lg font-bold uppercase tracking-wider text-ink">
          Cashiers
        </h2>
        <button
          type="button"
          onClick={() => setShowNew(true)}
          className="rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110"
        >
          + New User
        </button>
      </div>

      {users.isLoading && <p className="mt-4 text-ink-muted">Loading…</p>}
      {users.isError && (
        <p className="mt-4 text-status-danger">
          Could not load users. {users.error instanceof Error ? users.error.message : ""}
        </p>
      )}
      {users.data && (
        <table className="mt-4 w-full text-left">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase tracking-wider text-ink-muted">
              <th className="py-2">Username</th>
              <th className="py-2">Display name</th>
              <th className="py-2">Status</th>
              <th className="py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="users-tbody">
            {users.data.users.map((u) => (
              <UserRow
                key={u.username}
                user={u}
                isSelf={u.username === currentUsername}
                onResetPassword={() => setResetUser(u)}
                onAfterChange={invalidate}
              />
            ))}
          </tbody>
        </table>
      )}

      {showNew && (
        <NewUserModal
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            invalidate();
          }}
        />
      )}
      {resetUser && (
        <ResetPasswordModal
          user={resetUser}
          onClose={() => setResetUser(null)}
          onReset={() => {
            setResetUser(null);
            invalidate();
          }}
        />
      )}
    </div>
  );
}

function UserRow({
  user,
  isSelf,
  onResetPassword,
  onAfterChange,
}: {
  user: UserSummary;
  isSelf: boolean;
  onResetPassword: () => void;
  onAfterChange: () => void;
}) {
  const deactivate = useDeactivateUser();
  const [error, setError] = useState<string | null>(null);

  function handleDeactivate() {
    if (!window.confirm(`Deactivate ${user.username}? They will be signed out and locked out of the system.`)) return;
    setError(null);
    deactivate.mutate(user.username, {
      onSuccess: () => onAfterChange(),
      onError: (err) =>
        setError(err instanceof Error ? err.message : "Could not deactivate."),
    });
  }

  return (
    <tr className="border-b border-surface-border" data-testid={`user-row-${user.username}`}>
      <td className="py-3 font-mono font-bold text-ink">{user.username}</td>
      <td className="py-3 text-ink">{user.display_name}</td>
      <td className="py-3">
        {user.is_active ? (
          <span className="font-mono text-xs uppercase tracking-wider text-status-success">
            Active
          </span>
        ) : (
          <span className="font-mono text-xs uppercase tracking-wider text-ink-muted">
            Inactive
          </span>
        )}
        {user.must_change_password && (
          <span className="ml-2 font-mono text-[10px] uppercase tracking-wider text-status-warning">
            Pwd change required
          </span>
        )}
      </td>
      <td className="py-3 text-right">
        {user.is_active && !isSelf && (
          <>
            <button
              type="button"
              onClick={onResetPassword}
              className="mr-2 rounded-card border border-surface-border bg-surface px-3 py-1 font-mono text-xs font-bold uppercase tracking-wider text-ink hover:bg-surface-card"
            >
              Reset Pwd
            </button>
            <button
              type="button"
              onClick={handleDeactivate}
              disabled={deactivate.isPending}
              className="rounded-card border border-status-danger/50 bg-status-danger/10 px-3 py-1 font-mono text-xs font-bold uppercase tracking-wider text-status-danger hover:bg-status-danger/20 disabled:opacity-60"
            >
              Deactivate
            </button>
          </>
        )}
        {isSelf && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            (you)
          </span>
        )}
        {error && (
          <div className="mt-1 text-xs text-status-danger" role="alert">
            {error}
          </div>
        )}
      </td>
    </tr>
  );
}

function NewUserModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState<CreateUserRequest>({
    username: "",
    display_name: "",
    initial_password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const create = useCreateUser();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    create.mutate(form, {
      onSuccess: () => onCreated(),
      onError: (err) =>
        setError(err instanceof Error ? err.message : "Could not create user."),
    });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="New User"
      data-testid="new-user-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-card border border-surface-border bg-surface p-6 shadow-2xl"
      >
        <h2 className="font-mono text-base font-bold uppercase tracking-wider text-ink">
          New Cashier
        </h2>
        <div className="mt-4 space-y-3">
          <Field label="Username" required>
            <input
              type="text"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
              minLength={1}
              maxLength={64}
              aria-label="Username"
              className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-sm text-ink outline-none focus:border-brand-red"
            />
          </Field>
          <Field label="Display name" required>
            <input
              type="text"
              value={form.display_name}
              onChange={(e) => setForm({ ...form, display_name: e.target.value })}
              required
              minLength={1}
              maxLength={128}
              aria-label="Display name"
              className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 text-sm text-ink outline-none focus:border-brand-red"
            />
          </Field>
          <Field label="Initial password (≥8 chars)" required>
            <input
              type="text"
              value={form.initial_password}
              onChange={(e) =>
                setForm({ ...form, initial_password: e.target.value })
              }
              required
              minLength={8}
              maxLength={256}
              aria-label="Initial password"
              className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-sm text-ink outline-none focus:border-brand-red"
            />
          </Field>
        </div>
        <p className="mt-2 text-xs text-ink-muted">
          The cashier will be forced to change their password on first login.
        </p>
        {error && (
          <div role="alert" className="mt-3 text-xs text-status-danger">
            {error}
          </div>
        )}
        <div className="mt-5 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:opacity-60"
          >
            {create.isPending ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

function ResetPasswordModal({
  user,
  onClose,
  onReset,
}: {
  user: UserSummary;
  onClose: () => void;
  onReset: () => void;
}) {
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const reset = useResetUserPassword();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    reset.mutate(
      { username: user.username, new_password: newPassword },
      {
        onSuccess: () => onReset(),
        onError: (err) =>
          setError(err instanceof Error ? err.message : "Could not reset."),
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Reset password for ${user.username}`}
      data-testid="reset-password-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-card border border-surface-border bg-surface p-6 shadow-2xl"
      >
        <h2 className="font-mono text-base font-bold uppercase tracking-wider text-ink">
          Reset Password
        </h2>
        <p className="mt-2 text-sm text-ink-muted">
          Set a temporary password for{" "}
          <span className="font-mono font-bold text-ink">{user.username}</span>.
          They&apos;ll be forced to change it on next login.
        </p>
        <Field label="New password (≥8 chars)" required>
          <input
            type="text"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
            maxLength={256}
            aria-label="New password"
            className="mt-1 w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-sm text-ink outline-none focus:border-brand-red"
          />
        </Field>
        {error && (
          <div role="alert" className="mt-3 text-xs text-status-danger">
            {error}
          </div>
        )}
        <div className="mt-5 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={reset.isPending}
            className="rounded-card bg-brand-red px-4 py-2 font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:opacity-60"
          >
            {reset.isPending ? "Resetting…" : "Reset"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  required = false,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="font-mono text-xs font-bold uppercase tracking-wider text-ink-muted">
        {label}
        {required && " *"}
      </span>
      <span className="mt-1 block">{children}</span>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Till Sessions tab -- admin view of closed shifts
// ---------------------------------------------------------------------------

function TillSessionsTab() {
  const [statusFilter, setStatusFilter] = useState<"CLOSED" | "OPEN" | "">(
    "CLOSED",
  );
  const sessions = useTillSessions({ status: statusFilter });

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-center justify-between">
        <h2 className="font-mono text-lg font-bold uppercase tracking-wider text-ink">
          Till Sessions
        </h2>
        <select
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(e.target.value as "CLOSED" | "OPEN" | "")
          }
          aria-label="Filter by status"
          className="rounded-card border border-surface-border bg-surface px-3 py-1 font-mono text-xs uppercase tracking-wider text-ink"
        >
          <option value="CLOSED">Closed</option>
          <option value="OPEN">Open</option>
          <option value="">All</option>
        </select>
      </div>

      {sessions.isLoading && <p className="mt-4 text-ink-muted">Loading…</p>}
      {sessions.isError && (
        <p className="mt-4 text-status-danger">
          Could not load sessions.{" "}
          {sessions.error instanceof Error ? sessions.error.message : ""}
        </p>
      )}
      {sessions.data && sessions.data.sessions.length === 0 && (
        <p className="mt-4 text-ink-muted">No sessions match the filter.</p>
      )}
      {sessions.data && sessions.data.sessions.length > 0 && (
        <table className="mt-4 w-full text-left">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase tracking-wider text-ink-muted">
              <th className="py-2">Cashier</th>
              <th className="py-2">Opened</th>
              <th className="py-2">Closed</th>
              <th className="py-2 text-right">Opening</th>
              <th className="py-2 text-right">Counted</th>
              <th className="py-2 text-right">Variance</th>
              <th className="py-2 text-right">PDF</th>
            </tr>
          </thead>
          <tbody data-testid="sessions-tbody">
            {sessions.data.sessions.map((s) => (
              <tr key={s.session_id} className="border-b border-surface-border">
                <td className="py-3 font-mono font-bold text-ink">{s.cashier_id}</td>
                <td className="py-3 text-ink">
                  {new Date(s.opened_at).toLocaleString()}
                </td>
                <td className="py-3 text-ink">
                  {s.closed_at ? new Date(s.closed_at).toLocaleString() : "—"}
                </td>
                <td className="py-3 text-right font-mono text-ink">
                  {formatCents(s.opening_float_cents)}
                </td>
                <td className="py-3 text-right font-mono text-ink">
                  {s.closing_count_cents !== null
                    ? formatCents(s.closing_count_cents)
                    : "—"}
                </td>
                <td
                  className={`py-3 text-right font-mono font-bold ${varianceToneClass(s.variance_cents)}`}
                >
                  {s.variance_cents !== null
                    ? formatCents(s.variance_cents)
                    : "—"}
                </td>
                <td className="py-3 text-right">
                  {s.pdf_url ? (
                    <a
                      href={s.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-xs font-bold uppercase tracking-wider text-brand-red hover:underline"
                    >
                      PDF
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function varianceToneClass(cents: number | null): string {
  if (cents === null) return "text-ink-muted";
  const abs = Math.abs(cents);
  if (abs === 0) return "text-status-success";
  if (abs <= 500) return "text-status-warning";
  return "text-status-danger";
}
