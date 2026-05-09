import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import { CashTenderModal } from "../src/components/CashTenderModal";
import { useCheckout } from "../src/store/checkout";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

const COMPLETE_RESULT = {
  so_id: "SO-CASH-1",
  windcave_txn_ref: null,
  card_brand: null,
  card_last4: null,
  subtotal_cents: 19999,
  tax_cents: 1620,
  total_cents: 21619,
  payment_method: "cash",
  receipt_content: "(cash receipt)",
};

beforeEach(() => useCheckout.getState().reset());
afterEach(() => useCheckout.getState().reset());

function seedTendering(totalCents = 21619) {
  useCheckout.getState().startedCash("txn-cash-1", totalCents);
}

describe("<CashTenderModal>", () => {
  it("returns null when phase is not tendering_cash", () => {
    const { container } = renderWithQuery(<CashTenderModal />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the total due and starts with empty input", () => {
    seedTendering(21619);
    renderWithQuery(<CashTenderModal />);
    expect(screen.getByText(/total due/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/amount tendered/i)).toHaveValue(null);
    expect(screen.getByRole("button", { name: /^tender$/i })).toBeDisabled();
  });

  it("disables Tender until tendered >= total and updates change live", () => {
    seedTendering(21619);
    renderWithQuery(<CashTenderModal />);
    const input = screen.getByLabelText(/amount tendered/i);

    fireEvent.change(input, { target: { value: "200" } });
    expect(screen.getByRole("button", { name: /^tender$/i })).toBeDisabled();
    expect(screen.getByTestId("change-due")).toHaveTextContent("$0.00");

    fireEvent.change(input, { target: { value: "250" } });
    expect(screen.getByRole("button", { name: /^tender$/i })).toBeEnabled();
    expect(screen.getByTestId("change-due")).toHaveTextContent("$33.81");
  });

  it("Tender posts charge-cash, fetches /status for the receipt body, and lands the result with COMPLETE", async () => {
    server.use(
      http.post(`${API}/api/checkout/txn-cash-1/charge-cash`, () =>
        HttpResponse.json({
          transaction_id: "txn-cash-1",
          status: "COMPLETE",
          change_cents: 3381,
          so_id: "SO-CASH-1",
        }),
      ),
      http.get(`${API}/api/checkout/txn-cash-1/status`, () =>
        HttpResponse.json({
          transaction_id: "txn-cash-1",
          status: "COMPLETE",
          is_terminal: true,
          result: COMPLETE_RESULT,
        }),
      ),
    );

    seedTendering(21619);
    renderWithQuery(<CashTenderModal />);

    fireEvent.change(screen.getByLabelText(/amount tendered/i), {
      target: { value: "250" },
    });
    await userEvent.click(screen.getByRole("button", { name: /^tender$/i }));

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("result");
    });
    expect(useCheckout.getState().status).toBe("COMPLETE");
    expect(useCheckout.getState().result).toEqual(COMPLETE_RESULT);
  });

  it("Tender error lands the result with PAYMENT_FAILED carrying the error message", async () => {
    server.use(
      http.post(`${API}/api/checkout/txn-cash-1/charge-cash`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    seedTendering(21619);
    renderWithQuery(<CashTenderModal />);

    fireEvent.change(screen.getByLabelText(/amount tendered/i), {
      target: { value: "250" },
    });
    await userEvent.click(screen.getByRole("button", { name: /^tender$/i }));

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("result");
    });
    expect(useCheckout.getState().status).toBe("PAYMENT_FAILED");
  });

  it("Cancel posts /cancel and resets the checkout store", async () => {
    server.use(
      http.post(`${API}/api/checkout/txn-cash-1/cancel`, () =>
        HttpResponse.json({
          transaction_id: "txn-cash-1",
          status: "CANCELLED",
        }),
      ),
    );
    seedTendering(21619);
    renderWithQuery(<CashTenderModal />);

    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

    await waitFor(() => {
      expect(useCheckout.getState().phase).toBe("idle");
    });
  });

  it("preset buttons populate the tendered input with helpful round amounts", async () => {
    seedTendering(21619);
    renderWithQuery(<CashTenderModal />);

    const presets = screen.getAllByRole("button", { name: /^\$/ });
    expect(presets.length).toBeGreaterThanOrEqual(4);

    await userEvent.click(presets[0]);
    expect(screen.getByLabelText(/amount tendered/i)).toHaveValue(216.19);
  });
});
