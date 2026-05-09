import { type UserInfo, useLogout } from "../api/auth";
import { StatusStrip } from "../components/StatusStrip";

interface Props {
  user: UserInfo;
  onSignedOut: () => void;
}

export function RegisterScreen({ user, onSignedOut }: Props) {
  const logout = useLogout();

  function handleSignOut() {
    logout.mutate(undefined, {
      onSettled: onSignedOut,
    });
  }

  if (user.must_change_password) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface px-4">
        <div className="max-w-md rounded-card border border-brand-copper bg-surface-card p-8 text-center">
          <h1 className="mb-2 font-mono text-xl font-bold uppercase tracking-wider text-brand-red">
            Password change required
          </h1>
          <p className="text-sm text-ink-muted">
            The seeded admin/admin login forces a rotation before any other
            endpoint accepts the session. The change-password screen lands
            in the next commit.
          </p>
          <button
            type="button"
            onClick={handleSignOut}
            className="mt-6 rounded-card border border-surface-border bg-surface px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wider text-ink-muted hover:bg-surface-card"
          >
            Sign out
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <StatusStrip
        cashier={{ display_name: user.display_name }}
        onSignOut={handleSignOut}
        signOutPending={logout.isPending}
      />
      <main className="flex flex-1 items-center justify-center text-ink-muted">
        <div className="text-center">
          <p className="mb-1 font-mono text-lg uppercase tracking-wider text-ink">
            Register ready
          </p>
          <p className="text-sm">
            Cart, scan input, and pay panel land in the next commit.
          </p>
        </div>
      </main>
    </div>
  );
}
