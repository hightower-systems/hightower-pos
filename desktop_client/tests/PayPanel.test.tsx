import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import type { ItemLookupResponse } from "../src/api/items";
import { PayPanel } from "../src/components/PayPanel";
import { useCart } from "../src/store/cart";
import { useCheckout } from "../src/store/checkout";
import { useCustomer } from "../src/store/customer";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

const ROD: ItemLookupResponse = {
  sku: "ROD-100",
  name: "Premium Fly Rod",
  barcode: "1234567890",
  unit_price_cents: 19999,
  tax_rate: 0.0810,
  is_taxable: true,
  availability: [
    {
      warehouse_id: "WH-STORE",
      warehouse_name: "Store",
      qty_available: 5,
      bins: [{ bin_id: "BIN-A1", bin_name: "A1", qty: 5 }],
    },
  ],
};

beforeEach(() => {
  useCart.setState({ lines: [] });
  useCheckout.getState().reset();
  useCustomer.getState().reset();
});

afterEach(() => {
  useCart.setState({ lines: [] });
  useCheckout.getState().reset();
  useCustomer.getState().reset();
});

describe("<PayPanel>", () => {
  it("disables Pay Card when the cart is empty", () => {
    renderWithQuery(<PayPanel />);
    expect(screen.getByRole("button", { name: /pay with card/i })).toBeDisabled();
  });

  it("enables Pay Card when the cart has at least one line", () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<PayPanel />);
    expect(screen.getByRole("button", { name: /pay with card/i })).toBeEnabled();
  });

  it("Pay Cash is enabled when the cart has at least one line", () => {
    useCart.getState().addItem(ROD);
    renderWithQuery(<PayPanel />);
    expect(screen.getByRole("button", { name: /pay with cash/i })).toBeEnabled();
  });

  it("clicking Pay Cash runs start and transitions to tendering_cash with the total", async () => {
    server.use(
      http.post(`${API}/api/checkout/start`, () =>
        HttpResponse.json({
          transaction_id: "txn-cash-1",
          status: "AWAITING_PAYMENT",
          tax_rate: 0.0810,
          subtotal_cents: 19999,
          tax_cents: 1620,
          total_cents: 21619,
        }),
      ),
    );

    useCart.getState().addItem(ROD);
    renderWithQuery(<PayPanel />);

    await userEvent.click(screen.getByRole("button", { name: /pay with cash/i }));

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("tendering_cash");
    });
    expect(useCheckout.getState().transactionId).toBe("txn-cash-1");
    expect(useCheckout.getState().totalCents).toBe(21619);
  });

  it("clicking Pay Card runs start + charge-card and transitions checkout to in_flight", async () => {
    server.use(
      http.post(`${API}/api/checkout/start`, () =>
        HttpResponse.json({
          transaction_id: "txn-123",
          status: "AWAITING_PAYMENT",
          tax_rate: 0.0810,
          subtotal_cents: 19999,
          tax_cents: 1620,
          total_cents: 21619,
        }),
      ),
      http.post(`${API}/api/checkout/txn-123/charge-card`, () =>
        HttpResponse.json({
          transaction_id: "txn-123",
          status: "PAYMENT_IN_FLIGHT",
        }),
      ),
    );

    useCart.getState().addItem(ROD);
    renderWithQuery(<PayPanel />);

    await userEvent.click(screen.getByRole("button", { name: /pay with card/i }));

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("in_flight");
    });
    expect(useCheckout.getState().transactionId).toBe("txn-123");
  });

  it("includes the attached customer block in the /start payload", async () => {
    let captured: Record<string, unknown> = {};
    server.use(
      http.post(`${API}/api/checkout/start`, async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          transaction_id: "txn-c1",
          status: "AWAITING_PAYMENT",
          tax_rate: 0.0810,
          subtotal_cents: 19999,
          tax_cents: 1620,
          total_cents: 21619,
        });
      }),
      http.post(`${API}/api/checkout/txn-c1/charge-card`, () =>
        HttpResponse.json({
          transaction_id: "txn-c1",
          status: "PAYMENT_IN_FLIGHT",
        }),
      ),
    );

    useCart.getState().addItem(ROD);
    useCustomer.getState().setAttached({
      customer_id: "cust-1",
      name: "Pat Smith",
      email: "pat@example.com",
      phone: "+13035551234",
      registered: true,
    });
    renderWithQuery(<PayPanel />);

    await userEvent.click(screen.getByRole("button", { name: /pay with card/i }));

    await waitFor(() => {
      expect(captured.customer).toBeDefined();
    });
    expect(captured.customer).toEqual({
      customer_id: "cust-1",
      name: "Pat Smith",
      email: "pat@example.com",
      phone: "+13035551234",
    });
  });

  it("renders the failure path when /start returns 5xx", async () => {
    server.use(
      http.post(`${API}/api/checkout/start`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    useCart.getState().addItem(ROD);
    renderWithQuery(<PayPanel />);

    await userEvent.click(screen.getByRole("button", { name: /pay with card/i }));

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("result");
    });
    expect(useCheckout.getState().status).toBe("PAYMENT_FAILED");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
