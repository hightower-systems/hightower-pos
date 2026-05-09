import { type UserInfo, useLogout } from "../api/auth";
import { AttachCustomerModal } from "../components/AttachCustomerModal";
import { Cart } from "../components/Cart";
import { CartTotals } from "../components/CartTotals";
import { CashTenderModal } from "../components/CashTenderModal";
import { PayPanel } from "../components/PayPanel";
import { PaymentInFlight } from "../components/PaymentInFlight";
import { PaymentResult } from "../components/PaymentResult";
import { RefundConfirmModal } from "../components/RefundConfirmModal";
import { RefundInFlight } from "../components/RefundInFlight";
import { RefundLookupModal } from "../components/RefundLookupModal";
import { RefundResult } from "../components/RefundResult";
import { RegisterActions } from "../components/RegisterActions";
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

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <StatusStrip
        cashier={{ display_name: user.display_name }}
        onSignOut={handleSignOut}
        signOutPending={logout.isPending}
      />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 p-4 sm:p-6">
        <RegisterActions />
        <ScanInput />
        <div className="flex-1 overflow-auto">
          <Cart />
        </div>
        <CartTotals />
        <PayPanel />
      </main>
      <AttachCustomerModal />
      <CashTenderModal />
      <PaymentInFlight />
      <PaymentResult />
      <RefundLookupModal />
      <RefundConfirmModal />
      <RefundInFlight />
      <RefundResult />
    </div>
  );
}
