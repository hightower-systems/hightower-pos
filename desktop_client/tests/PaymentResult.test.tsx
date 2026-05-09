import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";

import type { ItemLookupResponse } from "../src/api/items";
import { PaymentResult } from "../src/components/PaymentResult";
import { useCart } from "../src/store/cart";
import { useCheckout } from "../src/store/checkout";
import { renderWithQuery } from "./utils";

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

beforeEach(() => {
  useCart.setState({ lines: [] });
  useCheckout.getState().reset();
});

afterEach(() => {
  useCart.setState({ lines: [] });
  useCheckout.getState().reset();
});

describe("<PaymentResult>", () => {
  it("returns null when the store is idle or in_flight", () => {
    const { container, rerender } = renderWithQuery(<PaymentResult />);
    expect(container).toBeEmptyDOMElement();

    useCheckout.getState().startedAt("txn-1");
    rerender(<PaymentResult />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the success view with total + card brand + last4 + SO id on COMPLETE", () => {
    useCheckout.getState().finished("COMPLETE", COMPLETE_RESULT, null);
    renderWithQuery(<PaymentResult />);

    expect(
      screen.getByRole("dialog", { name: /sale complete/i }),
    ).toBeInTheDocument();
    const success = screen.getByTestId("payment-success");
    expect(success).toHaveTextContent("$216.19");
    expect(success).toHaveTextContent(/visa/i);
    expect(success).toHaveTextContent(/4242/);
    expect(success).toHaveTextContent("SO-1");
  });

  it("renders the failure view with the error message on PAYMENT_FAILED", () => {
    useCheckout.getState().failed("Card declined");
    renderWithQuery(<PaymentResult />);

    expect(
      screen.getByRole("dialog", { name: /payment failed/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("payment-failure")).toHaveTextContent(
      /card declined/i,
    );
  });

  it("Done on success clears the cart and resets the checkout store", async () => {
    useCart.getState().addItem(ROD);
    useCheckout.getState().finished("COMPLETE", COMPLETE_RESULT, null);
    renderWithQuery(<PaymentResult />);

    await userEvent.click(screen.getByRole("button", { name: /done/i }));

    expect(useCart.getState().lines).toEqual([]);
    expect(useCheckout.getState().phase).toBe("idle");
  });

  it("Done on failure preserves the cart but resets the checkout store", async () => {
    useCart.getState().addItem(ROD);
    useCheckout.getState().failed("network error");
    renderWithQuery(<PaymentResult />);

    await userEvent.click(screen.getByRole("button", { name: /done/i }));

    expect(useCart.getState().lines).toHaveLength(1);
    expect(useCheckout.getState().phase).toBe("idle");
  });

  it("renders the right title for each non-COMPLETE terminal status", () => {
    const cases: Array<[string, RegExp]> = [
      ["VALIDATION_FAILED", /cart validation failed/i],
      ["INVENTORY_UPDATE_FAILED", /inventory update failed/i],
      ["CANCELLED", /payment cancelled/i],
    ];
    for (const [status, regex] of cases) {
      useCheckout.getState().finished(status, null, null);
      const { unmount } = renderWithQuery(<PaymentResult />);
      expect(screen.getByRole("dialog", { name: regex })).toBeInTheDocument();
      unmount();
      useCheckout.getState().reset();
    }
  });
});
