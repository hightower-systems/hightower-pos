import { type FormEvent, useState } from "react";

import { type UserInfo, useChangePassword, useLogout } from "../api/auth";
import { ApiError } from "../api/client";

interface Props {
  user: UserInfo;
  onChanged: (user: UserInfo) => void;
  onSignedOut: () => void;
}

const ERROR_LABELS: Record<string, string> = {
  invalid_credentials: "Current password is wrong.",
  new_password_must_differ:
    "Pick a new password that's different from the current one.",
  not_authenticated: "Session expired. Sign in again.",
};

function friendlyError(error: unknown, mismatch: boolean): string | null {
  if (mismatch) return "New passwords do not match.";
  if (!error) return null;
  if (error instanceof ApiError && error.code && ERROR_LABELS[error.code]) {
    return ERROR_LABELS[error.code];
  }
  return "Could not save the new password.";
}

export function ChangePasswordScreen({ user, onChanged, onSignedOut }: Props) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const change = useChangePassword();
  const logout = useLogout();

  const mismatch = next.length > 0 && confirm.length > 0 && next !== confirm;
  const errorMessage = friendlyError(change.error, mismatch);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!current || !next || !confirm) return;
    if (next !== confirm) return;
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: (info) => {
          setCurrent("");
          setNext("");
          setConfirm("");
          onChanged(info);
        },
      },
    );
  }

  function handleSignOut() {
    logout.mutate(undefined, { onSettled: onSignedOut });
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-card border border-surface-border bg-surface-card p-8 shadow-lg"
        aria-label="Change password"
      >
        <h1 className="mb-1 font-mono text-xl font-bold uppercase tracking-wider text-brand-red">
          Password change required
        </h1>
        <p className="mb-6 font-mono text-xs uppercase tracking-wider text-ink-muted">
          {user.username} -- pick a new password to continue
        </p>

        <Field
          label="Current password"
          value={current}
          onChange={setCurrent}
          autoFocus
          autoComplete="current-password"
        />
        <Field
          label="New password"
          value={next}
          onChange={setNext}
          autoComplete="new-password"
        />
        <Field
          label="Confirm new password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
        />

        <button
          type="submit"
          disabled={
            change.isPending ||
            !current ||
            !next ||
            !confirm ||
            next !== confirm
          }
          className="mt-2 min-h-[48px] w-full rounded-card bg-brand-red font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-brand-red focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {change.isPending ? "Saving..." : "Save new password"}
        </button>

        {errorMessage && (
          <p
            className="mt-4 rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 font-mono text-xs uppercase tracking-wider text-status-danger"
            role="alert"
          >
            {errorMessage}
          </p>
        )}

        <button
          type="button"
          onClick={handleSignOut}
          disabled={logout.isPending}
          className="mt-4 w-full rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card disabled:opacity-60"
        >
          Sign out
        </button>
      </form>
    </div>
  );
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
  autoComplete?: string;
}

function Field({ label, value, onChange, autoFocus, autoComplete }: FieldProps) {
  return (
    <label className="mb-4 block">
      <span className="mb-1 block font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted">
        {label}
      </span>
      <input
        type="password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        required
        aria-label={label}
        className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-ink outline-none focus:border-brand-red"
      />
    </label>
  );
}
