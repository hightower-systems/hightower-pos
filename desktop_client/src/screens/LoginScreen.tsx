import { type FormEvent, useState } from "react";

import { useLogin } from "../api/auth";
import { ApiError } from "../api/client";

interface Props {
  onSuccess: () => void;
}

const ERROR_LABELS: Record<string, string> = {
  invalid_credentials: "Wrong username or password.",
  not_authenticated: "Session expired. Sign in again.",
};

function friendlyError(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError && error.code && ERROR_LABELS[error.code]) {
    return ERROR_LABELS[error.code];
  }
  return "Could not reach the POS service. Try again.";
}

export function LoginScreen({ onSuccess }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ username, password }, { onSuccess });
  }

  const errorMessage = friendlyError(login.error);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-card border border-surface-border bg-surface-card p-8 shadow-lg"
        aria-label="Sign in"
      >
        <h1 className="mb-1 font-mono text-2xl font-bold uppercase tracking-wider text-ink">
          Hightower POS
        </h1>
        <p className="mb-6 font-mono text-xs uppercase tracking-wider text-brand-copper">
          Sign in to start the register
        </p>

        <label className="mb-4 block">
          <span className="mb-1 block font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Username
          </span>
          <input
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoFocus
            required
            autoComplete="username"
            className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-ink outline-none focus:border-brand-red"
          />
        </label>

        <label className="mb-6 block">
          <span className="mb-1 block font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted">
            Password
          </span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="current-password"
            className="w-full rounded-card border border-surface-inputBorder bg-surface-input px-3 py-2 font-mono text-ink outline-none focus:border-brand-red"
          />
        </label>

        <button
          type="submit"
          disabled={login.isPending}
          className="min-h-[48px] w-full rounded-card bg-brand-red font-mono text-sm font-bold uppercase tracking-wider text-brand-cream hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {login.isPending ? "Signing in..." : "Sign in"}
        </button>

        {errorMessage && (
          <p
            className="mt-4 rounded-card border border-status-danger/30 bg-status-danger/10 px-3 py-2 text-sm text-status-danger"
            role="alert"
          >
            {errorMessage}
          </p>
        )}
      </form>
    </div>
  );
}
