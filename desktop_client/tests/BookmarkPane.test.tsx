import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { BookmarkPane } from "../src/components/BookmarkPane";
import { useBookmarks } from "../src/store/bookmarks";
import { useCart } from "../src/store/cart";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

const ROD_LOOKUP = {
  sku: "ROD-100",
  name: "Premium Fly Rod",
  barcode: null,
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
  useBookmarks.getState().clear();
  useCart.setState({ lines: [] });
});

afterEach(() => {
  useBookmarks.getState().clear();
  useCart.setState({ lines: [] });
});

describe("<BookmarkPane>", () => {
  it("renders the empty state when there are no bookmarks", () => {
    renderWithQuery(<BookmarkPane />);
    expect(screen.getByTestId("bookmarks-empty")).toBeInTheDocument();
  });

  it("renders one tile per bookmarked SKU with sku and name visible", () => {
    useBookmarks.getState().add("ROD-100", "Premium Fly Rod");
    useBookmarks.getState().add("REEL-200", "Trout Reel");
    renderWithQuery(<BookmarkPane />);

    expect(screen.getByText("ROD-100")).toBeInTheDocument();
    expect(screen.getByText("Premium Fly Rod")).toBeInTheDocument();
    expect(screen.getByText("REEL-200")).toBeInTheDocument();
    expect(screen.getByText("Trout Reel")).toBeInTheDocument();
  });

  it("filters tiles by sku or name (case-insensitive)", async () => {
    useBookmarks.getState().add("ROD-100", "Premium Fly Rod");
    useBookmarks.getState().add("REEL-200", "Trout Reel");
    renderWithQuery(<BookmarkPane />);

    await userEvent.type(screen.getByLabelText(/filter bookmarks/i), "reel");
    expect(screen.queryByText("ROD-100")).not.toBeInTheDocument();
    expect(screen.getByText("REEL-200")).toBeInTheDocument();
  });

  it("clicking a tile fires items/lookup and adds the result to the cart", async () => {
    server.use(
      http.get(`${API}/api/items/lookup`, () => HttpResponse.json(ROD_LOOKUP)),
    );
    useBookmarks.getState().add("ROD-100", "Premium Fly Rod");
    renderWithQuery(<BookmarkPane />);

    await userEvent.click(
      screen.getByRole("button", { name: /add rod-100 to cart/i }),
    );

    await waitFor(() => {
      expect(useCart.getState().lines).toHaveLength(1);
    });
    expect(useCart.getState().lines[0].sku).toBe("ROD-100");
  });

  it("renders an inline error when the lookup fails", async () => {
    server.use(
      http.get(`${API}/api/items/lookup`, () =>
        HttpResponse.json(
          { detail: { error: "item_not_found" } },
          { status: 404 },
        ),
      ),
    );
    useBookmarks.getState().add("STALE-1", "Old SKU");
    renderWithQuery(<BookmarkPane />);

    await userEvent.click(
      screen.getByRole("button", { name: /add stale-1 to cart/i }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/stale-1/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/item not found/i);
  });

  it("× on a tile removes it from the bookmarks store", async () => {
    useBookmarks.getState().add("ROD-100", "Premium Fly Rod");
    renderWithQuery(<BookmarkPane />);

    await userEvent.click(
      screen.getByRole("button", { name: /remove rod-100 from bookmarks/i }),
    );

    expect(useBookmarks.getState().items).toEqual([]);
    expect(screen.getByTestId("bookmarks-empty")).toBeInTheDocument();
  });
});
