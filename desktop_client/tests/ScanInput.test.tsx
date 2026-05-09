import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { ScanInput } from "../src/components/ScanInput";
import { useCart } from "../src/store/cart";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

const SAMPLE_ITEM = {
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

beforeEach(() => useCart.setState({ lines: [] }));
afterEach(() => useCart.setState({ lines: [] }));

describe("<ScanInput>", () => {
  it("submits the scanned value, adds the item to the cart, and clears the input on success", async () => {
    server.use(
      http.get(`${API}/api/items/lookup`, () => HttpResponse.json(SAMPLE_ITEM)),
    );
    renderWithQuery(<ScanInput />);

    const input = screen.getByLabelText(/scan barcode or sku/i) as HTMLInputElement;
    await userEvent.type(input, "1234567890{Enter}");

    await waitFor(() => {
      expect(useCart.getState().lines).toHaveLength(1);
    });
    expect(useCart.getState().lines[0].sku).toBe("ROD-100");
    expect(input.value).toBe("");
  });

  it("renders a friendly 'Item not found' message on a 404 with item_not_found code", async () => {
    server.use(
      http.get(`${API}/api/items/lookup`, () =>
        HttpResponse.json(
          { detail: { error: "item_not_found" } },
          { status: 404 },
        ),
      ),
    );
    renderWithQuery(<ScanInput />);

    await userEvent.type(
      screen.getByLabelText(/scan barcode or sku/i),
      "missing{Enter}",
    );

    expect(await screen.findByText(/item not found/i)).toBeInTheDocument();
    expect(useCart.getState().lines).toHaveLength(0);
  });

  it("renders a generic error when the server is unreachable", async () => {
    server.use(
      http.get(`${API}/api/items/lookup`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    renderWithQuery(<ScanInput />);

    await userEvent.type(
      screen.getByLabelText(/scan barcode or sku/i),
      "anything{Enter}",
    );

    expect(
      await screen.findByText(/could not reach the pos service/i),
    ).toBeInTheDocument();
  });

  it("ignores empty submissions", async () => {
    renderWithQuery(<ScanInput />);
    await userEvent.type(
      screen.getByLabelText(/scan barcode or sku/i),
      "{Enter}",
    );
    expect(useCart.getState().lines).toHaveLength(0);
  });
});
