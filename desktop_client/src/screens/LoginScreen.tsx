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
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl"
        aria-label="Sign in"
      >
        <h1 className="mb-1 text-2xl font-semibold tracking-tight text-slate-100">
          AvidMax POS
        </h1>
        <p className="mb-6 text-sm text-slate-400">
          Sign in to start the register.
        </p>

        <label className="mb-4 block">
          <span className="mb-1 block text-sm text-slate-300">Username</span>
          <input
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoFocus
            required
            autoComplete="username"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-accent"
          />
        </label>

        <label className="mb-6 block">
          <span className="mb-1 block text-sm text-slate-300">Password</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="current-password"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-accent"
          />
        </label>

        <button
          type="submit"
          disabled={login.isPending}
          className="w-full rounded-lg bg-accent py-2 font-semibold text-accent-fg hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {login.isPending ? "Signing in..." : "Sign in"}
        </button>

        {errorMessage && (
          <p
            className="mt-4 rounded bg-red-900/40 px-3 py-2 text-sm text-red-200"
            role="alert"
          >
            {errorMessage}
          </p>
        )}
      </form>
    </div>
  );
}
