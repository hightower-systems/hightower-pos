import { type UserInfo, useLogout } from "../api/auth";
import { Cart } from "../components/Cart";
import { CartTotals } from "../components/CartTotals";
import { PayPanel } from "../components/PayPanel";
import { PaymentInFlight } from "../components/PaymentInFlight";
import { PaymentResult } from "../components/PaymentResult";
import { ScanInput } from "../components/ScanInput";
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
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-4 sm:p-6">
        <ScanInput />
        <div className="flex-1 overflow-auto">
          <Cart />
        </div>
        <CartTotals />
        <PayPanel />
      </main>
      <PaymentInFlight />
      <PaymentResult />
    </div>
  );
}
