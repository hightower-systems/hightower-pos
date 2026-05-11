import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { OpenTillModal } from "../src/components/OpenTillModal";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

describe("<OpenTillModal>", () => {
  it("returns null when open=false", () => {
    const { container } = renderWithQuery(
      <OpenTillModal open={false} onOpened={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("computes the total live as the cashier types denominations", async () => {
    renderWithQuery(<OpenTillModal open={true} onOpened={() => {}} />);
    expect(screen.getByTestId("open-till-total")).toHaveTextContent("$0.00");

    const u = userEvent.setup();
    // $50 x 1 + $20 x 5 + 25¢ x 4 = 50 + 100 + 1 = $151.00
    await u.type(screen.getByLabelText("Count of $50"), "1");
    await u.type(screen.getByLabelText("Count of $20"), "5");
    await u.type(screen.getByLabelText("Count of 25¢"), "4");
    expect(screen.getByTestId("open-till-total")).toHaveTextContent("$151.00");
  });

  it("posts denominations to /api/till/open and calls onOpened on success", async () => {
    const seen: unknown[] = [];
    server.use(
      http.post(`${API}/api/till/open`, async ({ request }) => {
        seen.push(await request.json());
        return HttpResponse.json({
          session_id: "sess-1",
          opening_float_cents: 5000,
          opened_at: "2026-05-11T18:00:00Z",
        });
      }),
    );
    const onOpened = vi.fn();
    renderWithQuery(<OpenTillModal open={true} onOpened={onOpened} />);
    await userEvent.setup().type(screen.getByLabelText("Count of $50"), "1");
    await userEvent.click(screen.getByRole("button", { name: /open till/i }));

    await waitFor(() => expect(onOpened).toHaveBeenCalledTimes(1));
    expect(seen).toEqual([
      { opening_denominations: expect.objectContaining({ fifty: 1 }) },
    ]);
  });

  it("surfaces a server error without calling onOpened", async () => {
    server.use(
      http.post(`${API}/api/till/open`, () =>
        HttpResponse.json(
          { detail: { error: "already_open" } },
          { status: 409 },
        ),
      ),
    );
    const onOpened = vi.fn();
    renderWithQuery(<OpenTillModal open={true} onOpened={onOpened} />);
    await userEvent.click(screen.getByRole("button", { name: /open till/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(onOpened).not.toHaveBeenCalled();
  });
});
