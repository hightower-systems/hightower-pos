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
      <CloseTillModal open={false} onClose={() => {}} onDoneAfterClose={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("computes variance live as the cashier types denominations", async () => {
    // expected = 100 + 45 - 5 = $140.00
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );

    const u = userEvent.setup();
    // $100 x 1 + $20 x 2 = $140.00 → BALANCED
    await u.type(screen.getByLabelText("Count of $100"), "1");
    await u.type(screen.getByLabelText("Count of $20"), "2");
    expect(screen.getByTestId("close-till-counted")).toHaveTextContent("$140.00");
    const variance = screen.getByTestId("close-till-variance");
    expect(variance).toHaveTextContent("BALANCED");
    // Color band: balanced -> green.
    expect(variance).toHaveAttribute("data-variance-tone", "balanced");
  });

  it("variance band is yellow within ±$5 and red beyond", async () => {
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );
    const u = userEvent.setup();
    // $100 + $20 + $20 - one penny on the cashier's side: counted
    // = 13999c, expected 14000c → short -$0.01, within ±$5 → small.
    await u.type(screen.getByLabelText("Count of $100"), "1");
    await u.type(screen.getByLabelText("Count of $20"), "1");
    await u.type(screen.getByLabelText("Count of 10¢"), "199");
    await u.type(screen.getByLabelText("Count of 1¢"), "9");
    const variance = screen.getByTestId("close-till-variance");
    // $100 + $20 + $19.90 + $0.09 = $139.99 → short $0.01
    expect(variance).toHaveTextContent("SHORT -$0.01");
    expect(variance).toHaveAttribute("data-variance-tone", "small");

    // Bump short to $10 → still inside the LARGE threshold (which is
    // > $10, not >= $10), so this is the boundary -- still 'large'
    // because $10.01 here. Clear inputs and try a $20 short instead.
    await u.clear(screen.getByLabelText("Count of $20"));
    await u.type(screen.getByLabelText("Count of $20"), "0");
    // Counted now = $100 + $19.90 + $0.09 = $119.99 → short -$20.01 -> large.
    expect(variance).toHaveAttribute("data-variance-tone", "large");
  });

  it("shows SHORT and signed variance when counted < expected", async () => {
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={() => {}} />,
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
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={() => {}} />,
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

  it("posts denominations to /api/till/close and shows the success screen with Print Report + Sign Out", async () => {
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
    const onDone = vi.fn();
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={onDone} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("Count of $100"), "1");
    await u.type(screen.getByLabelText("Count of $20"), "2");
    await u.click(screen.getByRole("button", { name: /^close till$/i }));

    // Success screen renders; onDoneAfterClose is NOT fired until
    // the cashier explicitly clicks Sign Out (so the PDF link is a
    // direct user gesture, not a deferred window.open).
    await waitFor(() =>
      expect(screen.getByTestId("close-till-success")).toBeInTheDocument(),
    );
    expect(onDone).not.toHaveBeenCalled();
    const printLink = screen.getByRole("link", { name: /print report/i });
    expect(printLink).toHaveAttribute("href", "/api/till/sessions/sess-1/pdf");
    expect(printLink).toHaveAttribute("target", "_blank");

    await u.click(screen.getByRole("button", { name: /sign out/i }));
    expect(onDone).toHaveBeenCalledTimes(1);

    expect(seen).toEqual([
      {
        closing_denominations: expect.objectContaining({
          hundred: 1,
          twenty: 2,
        }),
      },
    ]);
  });

  it("close with |variance| > $10 pops a confirm modal before submitting", async () => {
    // Mock the actual close handler so we can assert it only fires
    // after the cashier accepts the large-variance confirm.
    let closeCalls = 0;
    server.use(
      http.post(`${API}/api/till/close`, async () => {
        closeCalls += 1;
        return HttpResponse.json({
          session_id: "sess-1",
          status: "CLOSED",
          opening_float_cents: 10000,
          cash_sales_cents: 4500,
          cash_refunds_cents: 500,
          expected_closing_cents: 14000,
          closing_count_cents: 0,
          variance_cents: -14000,
          pdf_url: "/api/till/sessions/sess-1/pdf",
          closed_at: "2026-05-11T17:00:00Z",
        });
      }),
    );
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );
    // Counted is $0, expected $140 → short -$140.00, well past ±$10.
    const u = userEvent.setup();
    await u.click(screen.getByRole("button", { name: /^close till$/i }));

    // The confirm overlay is up; no network call yet.
    expect(screen.getByTestId("close-till-confirm-large")).toBeInTheDocument();
    expect(closeCalls).toBe(0);

    // Recount returns the cashier to the main form without submitting.
    await u.click(screen.getByRole("button", { name: /recount/i }));
    expect(screen.queryByTestId("close-till-confirm-large")).toBeNull();
    expect(closeCalls).toBe(0);

    // Hitting Close Till again pops the same confirm; accepting it
    // submits.
    await u.click(screen.getByRole("button", { name: /^close till$/i }));
    expect(screen.getByTestId("close-till-confirm-large")).toBeInTheDocument();
    await u.click(
      screen.getByRole("button", { name: /yes, close with this variance/i }),
    );
    await waitFor(() => expect(closeCalls).toBe(1));
  });

  it("close with small (<=$5) variance submits without the large-variance confirm", async () => {
    let closeCalls = 0;
    server.use(
      http.post(`${API}/api/till/close`, async () => {
        closeCalls += 1;
        return HttpResponse.json({
          session_id: "sess-1",
          status: "CLOSED",
          opening_float_cents: 10000,
          cash_sales_cents: 4500,
          cash_refunds_cents: 500,
          expected_closing_cents: 14000,
          closing_count_cents: 13999,
          variance_cents: -1,
          pdf_url: "/api/till/sessions/sess-1/pdf",
          closed_at: "2026-05-11T17:00:00Z",
        });
      }),
    );
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={() => {}} />,
    );
    await waitFor(() =>
      expect(screen.getByText("$140.00")).toBeInTheDocument(),
    );
    const u = userEvent.setup();
    // Counted = $139.99, $0.01 short -- inside ±$5, no confirm.
    await u.type(screen.getByLabelText("Count of $100"), "1");
    await u.type(screen.getByLabelText("Count of $20"), "1");
    await u.type(screen.getByLabelText("Count of 10¢"), "199");
    await u.type(screen.getByLabelText("Count of 1¢"), "9");
    await u.click(screen.getByRole("button", { name: /^close till$/i }));
    await waitFor(() => expect(closeCalls).toBe(1));
    expect(screen.queryByTestId("close-till-confirm-large")).toBeNull();
  });

  it("close button is disabled when no open session is present", async () => {
    // Override the seeded open till -- this case is current.status === "NONE".
    server.use(
      http.get(`${API}/api/till/current`, () =>
        HttpResponse.json({ status: "NONE" }),
      ),
    );
    renderWithQuery(
      <CloseTillModal open={true} onClose={() => {}} onDoneAfterClose={() => {}} />,
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /^close till$/i }),
      ).toBeDisabled();
    });
  });
});
