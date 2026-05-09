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
      <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
        <div className="max-w-md rounded-2xl border border-amber-700/40 bg-amber-900/10 p-8 text-center">
          <h1 className="mb-2 text-xl font-semibold text-amber-200">
            Password change required
          </h1>
          <p className="text-sm text-slate-300">
            The seeded admin/admin login forces a rotation before any other
            endpoint accepts the session. The change-password screen lands
            in the next commit.
          </p>
          <button
            type="button"
            onClick={handleSignOut}
            className="mt-6 rounded-lg border border-slate-700 px-4 py-2 text-slate-200 hover:bg-slate-800"
          >
            Sign out
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-950">
      <StatusStrip
        cashier={{ display_name: user.display_name }}
        onSignOut={handleSignOut}
        signOutPending={logout.isPending}
      />
      <main className="flex flex-1 items-center justify-center text-slate-500">
        <div className="text-center">
          <p className="mb-1 text-lg text-slate-300">Register ready.</p>
          <p className="text-sm">
            Cart, scan input, and pay panel land in the next commit.
          </p>
        </div>
      </main>
    </div>
  );
}
