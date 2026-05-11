import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type UserInfo, useLogout } from "../api/auth";
import { useCurrentTill } from "../api/till";
import { AttachCustomerModal } from "../components/AttachCustomerModal";
import { BookmarkPane } from "../components/BookmarkPane";
import { Cart } from "../components/Cart";
import { CartTotals } from "../components/CartTotals";
import { CashTenderModal } from "../components/CashTenderModal";
import { CloseTillModal } from "../components/CloseTillModal";
import { OpenTillModal } from "../components/OpenTillModal";
import { PayPanel } from "../components/PayPanel";
import { PaymentInFlight } from "../components/PaymentInFlight";
import { PaymentResult } from "../components/PaymentResult";
import { RefundConfirmModal } from "../components/RefundConfirmModal";
import { RefundInFlight } from "../components/RefundInFlight";
import { RefundLookupModal } from "../components/RefundLookupModal";
import { RefundResult } from "../components/RefundResult";
import { RegisterActions } from "../components/RegisterActions";
import { ScanInput } from "../components/ScanInput";
import { SplitPane } from "../components/SplitPane";
import { StatusStrip } from "../components/StatusStrip";

interface Props {
  user: UserInfo;
  onSignedOut: () => void;
  // Optional so existing tests that don't care about settings can
  // skip the prop. When omitted, the StatusStrip simply doesn't
  // render a Settings button.
  onOpenSettings?: () => void;
}

export function RegisterScreen({ user, onSignedOut, onOpenSettings }: Props) {
  const logout = useLogout();
  const queryClient = useQueryClient();
  // Authoritative source for till state on the register screen.
  // /me carries a brief on initial load; this query keeps the
  // running tallies (cash_sales, expected_closing) fresh while the
  // close modal is open or the cashier checks the header label.
  const till = useCurrentTill();
  const [closeOpen, setCloseOpen] = useState(false);

  const tillIsOpen = till.data?.status === "OPEN";

  async function handleSignOut() {
    const result = await logout.mutateAsync();
    if (result.warning === "open_till_session") {
      const proceed = window.confirm(
        "You have an open till. Sign out anyway? You'll need to close it next time you log in.",
      );
      if (!proceed) {
        // Re-establish the session by refetching /me. The cookie was
        // cleared by the server, so the next /me will 401 and route
        // them back to login -- not ideal but matches the doc's
        // 'logout doesn't block' rule (the cookie clear is the
        // server's commitment; we can't un-revoke).
        onSignedOut();
        return;
      }
    }
    onSignedOut();
  }

  function handleTillOpened() {
    // Invalidate so the header + register UI pick up the new state
    // without forcing a full page reload.
    void queryClient.invalidateQueries({ queryKey: ["till", "current"] });
    void queryClient.invalidateQueries({ queryKey: ["me"] });
  }

  function handleDoneAfterClose() {
    // Triggered by the cashier's explicit Sign Out click on the
    // close-success screen. The PDF (if they wanted it) has already
    // been opened in a new tab on their own gesture via the success
    // screen's Print Report link.
    setCloseOpen(false);
    void queryClient.invalidateQueries({ queryKey: ["till", "current"] });
    void queryClient.invalidateQueries({ queryKey: ["me"] });
    logout.mutate(undefined, {
      onSettled: () => {
        onSignedOut();
      },
    });
  }

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <StatusStrip
        cashier={{ display_name: user.display_name }}
        onSignOut={() => void handleSignOut()}
        signOutPending={logout.isPending}
        onOpenSettings={onOpenSettings}
        till={
          tillIsOpen && till.data?.status === "OPEN"
            ? {
                opening_float_cents: till.data.opening_float_cents,
                onCloseTill: () => setCloseOpen(true),
              }
            : null
        }
      />
      <SplitPane
        storageKey="hightower-pos.split-right-width"
        defaultRightWidth={360}
        minLeftWidth={520}
        minRightWidth={240}
        maxRightWidth={720}
        left={
          <main className="flex w-full flex-1 flex-col gap-4 overflow-auto p-4 sm:p-6">
            <RegisterActions />
            <ScanInput />
            <div className="flex-1 overflow-auto">
              <Cart />
            </div>
            <CartTotals />
            <PayPanel />
          </main>
        }
        right={<BookmarkPane />}
      />
      <AttachCustomerModal />
      <CashTenderModal />
      <PaymentInFlight />
      <PaymentResult />
      <RefundLookupModal />
      <RefundConfirmModal />
      <RefundInFlight />
      <RefundResult />
      {/* Till modals: Open is blocking until a session is open;
          Close is on-demand from the header. */}
      <OpenTillModal
        open={till.isSuccess && !tillIsOpen}
        onOpened={handleTillOpened}
      />
      <CloseTillModal
        open={closeOpen}
        onClose={() => setCloseOpen(false)}
        onDoneAfterClose={handleDoneAfterClose}
      />
    </div>
  );
}
