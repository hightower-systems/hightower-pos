import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { RefundConfirmModal } from "../src/components/RefundConfirmModal";
import { RefundInFlight } from "../src/components/RefundInFlight";
import { RefundLookupModal } from "../src/components/RefundLookupModal";
import { RefundResult } from "../src/components/RefundResult";
import { useRefund, type RefundLookup } from "../src/store/refund";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";
const PRINT_AGENT = "http://localhost/print-agent";

const ORIGINAL_CARD: RefundLookup = {
  original_transaction_id: "txn-123",
  original_sentry_so_id: "SO-1",
  completed_at: "2026-05-09T18:00:00",
  payment_method: "card",
  card_brand: "VISA",
  card_last4: "4242",
  subtotal_cents: 19999,
  tax_cents: 1620,
  total_cents: 21619,
  lines: [{ sku: "ROD-100", quantity: 1 }],
  refundable: true,
};

const ORIGINAL_CASH: RefundLookup = {
  ...ORIGINAL_CARD,
  payment_method: "cash",
  card_brand: null,
  card_last4: null,
};

const REFUND_RESULT_CARD = {
  refund_so_id: "SO-R-1",
  windcave_txn_ref: "WC-R-1",
  card_brand: "VISA",
  card_last4: "4242",
  subtotal_cents: 19999,
  tax_cents: 1620,
  total_cents: 21619,
  payment_method: "card",
  receipt_content: "(refund receipt)",
};

beforeEach(() => useRefund.getState().reset());
afterEach(() => useRefund.getState().reset());

describe("<RefundLookupModal>", () => {
  it("returns null when phase is idle", () => {
    const { container } = renderWithQuery(<RefundLookupModal />);
    expect(container).toBeEmptyDOMElement();
  });

  it("submits the txn id, transitions to confirm on success", async () => {
    server.use(
      http.get(`${API}/api/refunds/lookup`, () =>
        HttpResponse.json(ORIGINAL_CARD),
      ),
    );
    useRefund.getState().openLookup();
    renderWithQuery(<RefundLookupModal />);

    await userEvent.type(
      screen.getByLabelText(/original transaction id/i),
      "txn-123",
    );
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));

    await waitFor(() => {
      expect(useRefund.getState().phase).toBe("confirm");
    });
    expect(useRefund.getState().original).toEqual(ORIGINAL_CARD);
  });

  it("renders the not-refundable warning when lookup says refundable=false", async () => {
    server.use(
      http.get(`${API}/api/refunds/lookup`, () =>
        HttpResponse.json({ ...ORIGINAL_CARD, refundable: false }),
      ),
    );
    useRefund.getState().openLookup();
    renderWithQuery(<RefundLookupModal />);

    await userEvent.type(
      screen.getByLabelText(/original transaction id/i),
      "txn-old",
    );
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));

    expect(await screen.findByText(/not refundable/i)).toBeInTheDocument();
    expect(useRefund.getState().phase).toBe("lookup");
  });
});

describe("<RefundConfirmModal>", () => {
  it("returns null when phase is not confirm", () => {
    const { container } = renderWithQuery(<RefundConfirmModal />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the locked tender and the refund total for a card original", () => {
    useRefund.getState().loaded(ORIGINAL_CARD);
    renderWithQuery(<RefundConfirmModal />);
    expect(screen.getByText(/tender \(locked\)/i)).toBeInTheDocument();
    expect(screen.getByText(/visa/i)).toBeInTheDocument();
    expect(screen.getByText(/4242/)).toBeInTheDocument();
    expect(screen.getByText("$216.19")).toBeInTheDocument();
  });

  it("Refund on a card original lands in_flight after start + charge-card", async () => {
    server.use(
      http.post(`${API}/api/refunds/start`, () =>
        HttpResponse.json({
          refund_transaction_id: "refund-txn-1",
          status: "REFUND_PENDING",
          payment_method: "card",
          subtotal_cents: 19999,
          tax_cents: 1620,
          total_cents: 21619,
        }),
      ),
      http.post(`${API}/api/refunds/refund-txn-1/charge-card`, () =>
        HttpResponse.json({
          refund_transaction_id: "refund-txn-1",
          status: "REFUND_PAYMENT_IN_FLIGHT",
        }),
      ),
    );
    useRefund.getState().loaded(ORIGINAL_CARD);
    renderWithQuery(<RefundConfirmModal />);

    await userEvent.click(screen.getByRole("button", { name: /^refund$/i }));

    await waitFor(() => {
      expect(useRefund.getState().phase).toBe("in_flight");
    });
    expect(useRefund.getState().refundTransactionId).toBe("refund-txn-1");
  });

  it("Refund on a cash original goes start + charge-cash + status, lands COMPLETE", async () => {
    server.use(
      http.post(`${API}/api/refunds/start`, () =>
        HttpResponse.json({
          refund_transaction_id: "refund-txn-2",
          status: "REFUND_PENDING",
          payment_method: "cash",
          subtotal_cents: 19999,
          tax_cents: 1620,
          total_cents: 21619,
        }),
      ),
      http.post(`${API}/api/refunds/refund-txn-2/charge-cash`, () =>
        HttpResponse.json({
          refund_transaction_id: "refund-txn-2",
          status: "COMPLETE",
          refund_so_id: "SO-R-1",
        }),
      ),
      http.get(`${API}/api/refunds/refund-txn-2/status`, () =>
        HttpResponse.json({
          refund_transaction_id: "refund-txn-2",
          status: "COMPLETE",
          is_terminal: true,
          result: { ...REFUND_RESULT_CARD, payment_method: "cash" },
        }),
      ),
    );
    useRefund.getState().loaded(ORIGINAL_CASH);
    renderWithQuery(<RefundConfirmModal />);

    await userEvent.click(screen.getByRole("button", { name: /^refund$/i }));

    await waitFor(() => {
      expect(useRefund.getState().phase).toBe("result");
    });
    expect(useRefund.getState().status).toBe("COMPLETE");
  });

  it("a 5xx on /start lands the store in result with REFUND_PAYMENT_FAILED", async () => {
    server.use(
      http.post(`${API}/api/refunds/start`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    useRefund.getState().loaded(ORIGINAL_CARD);
    renderWithQuery(<RefundConfirmModal />);

    await userEvent.click(screen.getByRole("button", { name: /^refund$/i }));

    await waitFor(() => {
      expect(useRefund.getState().phase).toBe("result");
    });
    expect(useRefund.getState().status).toBe("REFUND_PAYMENT_FAILED");
  });
});

describe("<RefundInFlight>", () => {
  it("returns null when not in_flight", () => {
    const { container } = renderWithQuery(<RefundInFlight />);
    expect(container).toBeEmptyDOMElement();
  });

  it("transitions to result on the first terminal poll", async () => {
    server.use(
      http.get(`${API}/api/refunds/refund-1/status`, () =>
        HttpResponse.json({
          refund_transaction_id: "refund-1",
          status: "COMPLETE",
          is_terminal: true,
          result: REFUND_RESULT_CARD,
        }),
      ),
    );
    useRefund.getState().startedCardRefund("refund-1");
    renderWithQuery(<RefundInFlight />);

    await waitFor(() => {
      expect(useRefund.getState().phase).toBe("result");
    });
    expect(useRefund.getState().result).toEqual(REFUND_RESULT_CARD);
  });
});

describe("<RefundResult>", () => {
  it("returns null when phase is not result", () => {
    const { container } = renderWithQuery(<RefundResult />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the success view with refunded total + brand + last4 + SO id", () => {
    useRefund.getState().finished("COMPLETE", REFUND_RESULT_CARD, null);
    renderWithQuery(<RefundResult />);

    expect(
      screen.getByRole("dialog", { name: /refund complete/i }),
    ).toBeInTheDocument();
    const success = screen.getByTestId("refund-success");
    expect(success).toHaveTextContent("$216.19");
    expect(success).toHaveTextContent(/visa/i);
    expect(success).toHaveTextContent(/4242/);
    expect(success).toHaveTextContent("SO-R-1");
  });

  it("auto-prints the refund receipt with open_drawer_after=true for cash refunds", async () => {
    let captured: { open_drawer_after?: boolean } = {};
    server.use(
      http.post(`${PRINT_AGENT}/print`, async ({ request }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json({ success: true, printer_status: "online" });
      }),
    );

    useRefund.getState().finished(
      "COMPLETE",
      { ...REFUND_RESULT_CARD, payment_method: "cash" },
      null,
    );
    renderWithQuery(<RefundResult />);

    await waitFor(() => {
      expect(captured.open_drawer_after).toBe(true);
    });
  });

  it("does not auto-print on REFUND_PAYMENT_FAILED", async () => {
    let printCalled = false;
    server.use(
      http.post(`${PRINT_AGENT}/print`, () => {
        printCalled = true;
        return HttpResponse.json({ success: true, printer_status: "online" });
      }),
    );

    useRefund.getState().failed("declined");
    renderWithQuery(<RefundResult />);
    await new Promise((r) => setTimeout(r, 50));
    expect(printCalled).toBe(false);
  });

  it("Done resets the refund store", async () => {
    useRefund.getState().finished("COMPLETE", REFUND_RESULT_CARD, null);
    renderWithQuery(<RefundResult />);
    await userEvent.click(screen.getByRole("button", { name: /done/i }));
    expect(useRefund.getState().phase).toBe("idle");
  });
});
