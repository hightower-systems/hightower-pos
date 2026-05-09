import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { PaymentInFlight } from "../src/components/PaymentInFlight";
import { useCheckout } from "../src/store/checkout";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

const COMPLETE_RESULT = {
  so_id: "SO-1",
  windcave_txn_ref: "WC-1",
  card_brand: "VISA",
  card_last4: "4242",
  subtotal_cents: 19999,
  tax_cents: 1620,
  total_cents: 21619,
  payment_method: "card",
  receipt_content: "(receipt)",
};

beforeEach(() => useCheckout.getState().reset());
afterEach(() => useCheckout.getState().reset());

describe("<PaymentInFlight>", () => {
  it("returns null when the checkout store is idle", () => {
    const { container } = renderWithQuery(<PaymentInFlight />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the dialog and the payment-in-flight prompt when the store is in_flight", async () => {
    server.use(
      http.get(`${API}/api/checkout/txn-123/status`, () =>
        HttpResponse.json({
          transaction_id: "txn-123",
          status: "PAYMENT_IN_FLIGHT",
          is_terminal: false,
          result: null,
        }),
      ),
    );

    useCheckout.getState().startedAt("txn-123");
    renderWithQuery(<PaymentInFlight />);

    expect(
      await screen.findByRole("dialog", { name: /card payment/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/tap, insert, or swipe the card/i),
    ).toBeInTheDocument();
  });

  it("transitions to result when the polled status reports is_terminal=true", async () => {
    server.use(
      http.get(`${API}/api/checkout/txn-123/status`, () =>
        HttpResponse.json({
          transaction_id: "txn-123",
          status: "COMPLETE",
          is_terminal: true,
          result: COMPLETE_RESULT,
        }),
      ),
    );

    useCheckout.getState().startedAt("txn-123");
    renderWithQuery(<PaymentInFlight />);

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("result");
    });
    expect(useCheckout.getState().status).toBe("COMPLETE");
    expect(useCheckout.getState().result).toEqual(COMPLETE_RESULT);
  });

  it("Cancel calls POST /cancel; subsequent terminal status flips to result", async () => {
    let cancelled = false;
    server.use(
      http.post(`${API}/api/checkout/txn-123/cancel`, () => {
        cancelled = true;
        return HttpResponse.json({
          transaction_id: "txn-123",
          status: "CANCELLED",
        });
      }),
      http.get(`${API}/api/checkout/txn-123/status`, () =>
        HttpResponse.json({
          transaction_id: "txn-123",
          status: cancelled ? "CANCELLED" : "PAYMENT_IN_FLIGHT",
          is_terminal: cancelled,
          result: null,
        }),
      ),
    );

    useCheckout.getState().startedAt("txn-123");
    renderWithQuery(<PaymentInFlight />);

    await screen.findByRole("dialog", { name: /card payment/i });
    await userEvent.click(screen.getByRole("button", { name: /^cancel$/i }));

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("result");
    });
    expect(useCheckout.getState().status).toBe("CANCELLED");
  });
});
