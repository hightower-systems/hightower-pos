import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { CloseTillModal } from "../src/components/CloseTillModal";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

function seedOpenTill(opts: Partial<{
  opening: number;
  sales: number;
  refunds: number;
}> = {}) {
  const { opening = 10000, sales = 4500, refunds = 500 } = opts;
  server.use(
    http.get(`${API}/api/till/current`, () =>
      HttpResponse.json({
        status: "OPEN",
        session_id: "sess-1",
        opening_float_cents: opening,
        cash_sales_cents: sales,
        cash_refunds_cents: refunds,
        transaction_count: 7,
        cash_transaction_count: 3,
        expected_closing_cents: opening + sales - refunds,
        opened_at: "2026-05-11T08:00:00Z",
      }),
    ),
  );
}

beforeEach(() => seedOpenTill());
afterEach(() => {});

describe("<CloseTillModal>", () => {
  it("returns null when open=false", () => {
    const { container } = renderWithQuery(
      <CloseTillModal open={false} onClose={() => {}} onClosed={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("computes variance live as the cashier types denominations", async () => {
    // expected = 100 + 45 - 5 = $140.00
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onClosed={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );

    const u = userEvent.setup();
    // $100 x 1 + $20 x 2 = $140.00 → BALANCED
    await u.type(screen.getByLabelText("Count of $100"), "1");
    await u.type(screen.getByLabelText("Count of $20"), "2");
    expect(screen.getByTestId("close-till-counted")).toHaveTextContent("$140.00");
    expect(screen.getByTestId("close-till-variance")).toHaveTextContent("BALANCED");
  });

  it("shows SHORT and signed variance when counted < expected", async () => {
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onClosed={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );
    await userEvent.setup().type(
      screen.getByLabelText("Count of $100"),
      "1",
    );
    // Counted = $100, expected $140 → short -$40.00.
    expect(screen.getByTestId("close-till-variance")).toHaveTextContent(
      "SHORT -$40.00",
    );
  });

  it("shows OVER and signed variance when counted > expected", async () => {
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onClosed={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("Count of $100"), "2");
    expect(screen.getByTestId("close-till-variance")).toHaveTextContent(
      "OVER $60.00",
    );
  });

  it("posts denominations to /api/till/close and hands the pdf_url to onClosed", async () => {
    const seen: unknown[] = [];
    server.use(
      http.post(`${API}/api/till/close`, async ({ request }) => {
        seen.push(await request.json());
        return HttpResponse.json({
          session_id: "sess-1",
          status: "CLOSED",
          opening_float_cents: 10000,
          cash_sales_cents: 4500,
          cash_refunds_cents: 500,
          expected_closing_cents: 14000,
          closing_count_cents: 14000,
          variance_cents: 0,
          pdf_url: "/api/till/sessions/sess-1/pdf",
          closed_at: "2026-05-11T17:00:00Z",
        });
      }),
    );
    const onClosed = vi.fn();
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onClosed={onClosed} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("Count of $100"), "1");
    await u.type(screen.getByLabelText("Count of $20"), "2");
    await u.click(screen.getByRole("button", { name: /^close till$/i }));

    await waitFor(() => expect(onClosed).toHaveBeenCalledTimes(1));
    expect(onClosed).toHaveBeenCalledWith("/api/till/sessions/sess-1/pdf");
    expect(seen).toEqual([
      {
        closing_denominations: expect.objectContaining({
          hundred: 1,
          twenty: 2,
        }),
      },
    ]);
  });

  it("close button is disabled when no open session is present", async () => {
    // Override the seeded open till -- this case is current.status === "NONE".
    server.use(
      http.get(`${API}/api/till/current`, () =>
        HttpResponse.json({ status: "NONE" }),
      ),
    );
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onClosed={() => {}} />,
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^close till$/i }),
      ).toBeDisabled();
    });
  });
});
