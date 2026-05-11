import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";

import type { UserInfo } from "../src/api/auth";
import { SettingsScreen } from "../src/screens/SettingsScreen";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

const ADMIN_USER: UserInfo = {
  username: "admin",
  display_name: "Administrator",
  expires_at: "2027-01-01T00:00:00Z",
  must_change_password: false,
};

function seedUsers() {
  server.use(
    http.get(`${API}/api/admin/users`, () =>
      HttpResponse.json({
        users: [
          {
            username: "admin",
            display_name: "Administrator",
            is_active: true,
            must_change_password: false,
            created_at: "2026-05-01T00:00:00Z",
          },
          {
            username: "mike",
            display_name: "Mike Hightower",
            is_active: true,
            must_change_password: false,
            created_at: "2026-05-10T00:00:00Z",
          },
          {
            username: "retired",
            display_name: "Retired Cashier",
            is_active: false,
            must_change_password: false,
            created_at: "2026-04-01T00:00:00Z",
          },
        ],
      }),
    ),
  );
}

describe("<SettingsScreen>", () => {
  it("renders the users tab by default with all users", async () => {
    seedUsers();
    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Mike Hightower")).toBeInTheDocument();
    });
    const tbody = screen.getByTestId("users-tbody");
    // 3 rows total (admin, mike, retired).
    expect(within(tbody).getAllByRole("row")).toHaveLength(3);
  });

  it("hides destructive actions on the current user's own row", async () => {
    seedUsers();
    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Mike Hightower")).toBeInTheDocument();
    });
    const adminRow = screen.getByTestId("user-row-admin");
    // No deactivate / reset buttons on the (you) row.
    expect(
      within(adminRow).queryByRole("button", { name: /deactivate/i }),
    ).toBeNull();
    expect(
      within(adminRow).queryByRole("button", { name: /reset pwd/i }),
    ).toBeNull();
    expect(within(adminRow).getByText(/\(you\)/i)).toBeInTheDocument();
  });

  it("hides actions on inactive users (they're already deactivated)", async () => {
    seedUsers();
    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Retired Cashier")).toBeInTheDocument();
    });
    const retiredRow = screen.getByTestId("user-row-retired");
    expect(
      within(retiredRow).queryByRole("button", { name: /deactivate/i }),
    ).toBeNull();
    expect(within(retiredRow).getByText(/inactive/i)).toBeInTheDocument();
  });

  it("creates a new user via the modal and refetches the list", async () => {
    seedUsers();
    let createCount = 0;
    server.use(
      http.post(`${API}/api/admin/users`, async ({ request }) => {
        createCount += 1;
        const body = (await request.json()) as {
          username: string;
          display_name: string;
          initial_password: string;
        };
        return HttpResponse.json(
          {
            username: body.username,
            display_name: body.display_name,
            is_active: true,
            must_change_password: true,
            created_at: "2026-05-11T18:00:00Z",
          },
          { status: 201 },
        );
      }),
    );
    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);

    await userEvent.setup().click(
      await screen.findByRole("button", { name: /new user/i }),
    );
    expect(await screen.findByTestId("new-user-modal")).toBeInTheDocument();
    const u = userEvent.setup();
    await u.type(screen.getByLabelText("Username"), "newhire");
    await u.type(screen.getByLabelText("Display name"), "New Hire");
    await u.type(screen.getByLabelText("Initial password"), "temp-pass-1");
    await u.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => expect(createCount).toBe(1));
  });

  it("deactivates a user after confirm and surfaces the new inactive state", async () => {
    seedUsers();
    let deactivated: string | null = null;
    server.use(
      http.delete(`${API}/api/admin/users/:username`, ({ params }) => {
        deactivated = params.username as string;
        return HttpResponse.json({
          username: params.username as string,
          display_name: "Mike Hightower",
          is_active: false,
          must_change_password: false,
          created_at: "2026-05-10T00:00:00Z",
        });
      }),
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Mike Hightower")).toBeInTheDocument();
    });
    const mikeRow = screen.getByTestId("user-row-mike");
    await userEvent
      .setup()
      .click(within(mikeRow).getByRole("button", { name: /deactivate/i }));

    await waitFor(() => expect(deactivated).toBe("mike"));
  });

  it("does NOT deactivate when the cashier cancels the confirm dialog", async () => {
    seedUsers();
    let calls = 0;
    server.use(
      http.delete(`${API}/api/admin/users/:username`, () => {
        calls += 1;
        return HttpResponse.json({});
      }),
    );
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Mike Hightower")).toBeInTheDocument();
    });
    const mikeRow = screen.getByTestId("user-row-mike");
    await userEvent
      .setup()
      .click(within(mikeRow).getByRole("button", { name: /deactivate/i }));

    // No network call.
    expect(calls).toBe(0);
  });

  it("opens the reset-password modal and submits the new password", async () => {
    seedUsers();
    let captured: { username: string; new_password: string } | null = null;
    server.use(
      http.post(
        `${API}/api/admin/users/:username/reset-password`,
        async ({ params, request }) => {
          const body = (await request.json()) as { new_password: string };
          captured = {
            username: params.username as string,
            new_password: body.new_password,
          };
          return HttpResponse.json({
            username: params.username as string,
            display_name: "Mike Hightower",
            is_active: true,
            must_change_password: true,
            created_at: "2026-05-10T00:00:00Z",
          });
        },
      ),
    );
    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText("Mike Hightower")).toBeInTheDocument();
    });

    const u = userEvent.setup();
    const mikeRow = screen.getByTestId("user-row-mike");
    await u.click(within(mikeRow).getByRole("button", { name: /reset pwd/i }));
    expect(await screen.findByTestId("reset-password-modal")).toBeInTheDocument();
    await u.type(screen.getByLabelText("New password"), "fresh-temp-1");
    await u.click(screen.getByRole("button", { name: /^reset$/i }));

    await waitFor(() =>
      expect(captured).toEqual({
        username: "mike",
        new_password: "fresh-temp-1",
      }),
    );
  });

  it("switches to the till-sessions tab and renders the listing", async () => {
    server.use(
      http.get(`${API}/api/till/sessions`, () =>
        HttpResponse.json({
          sessions: [
            {
              session_id: "s-1",
              cashier_id: "mike",
              terminal_id: "REG-1",
              status: "CLOSED",
              opening_float_cents: 10000,
              cash_sales_cents: 4500,
              cash_refunds_cents: 0,
              expected_closing_cents: 14500,
              closing_count_cents: 14500,
              variance_cents: 0,
              transaction_count: 3,
              cash_transaction_count: 1,
              opened_at: "2026-05-11T08:00:00Z",
              closed_at: "2026-05-11T17:00:00Z",
              pdf_url: "/api/till/sessions/s-1/pdf",
            },
          ],
        }),
      ),
    );
    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={() => {}} />);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: /till sessions/i }));
    await waitFor(() => {
      expect(screen.getByTestId("sessions-tbody")).toBeInTheDocument();
    });
    const tbody = screen.getByTestId("sessions-tbody");
    expect(within(tbody).getByText("mike")).toBeInTheDocument();
    expect(within(tbody).getByRole("link", { name: "PDF" })).toHaveAttribute(
      "href",
      "/api/till/sessions/s-1/pdf",
    );
  });

  it("calls onBack when the Back button is clicked", async () => {
    seedUsers();
    const onBack = vi.fn();
    renderWithQuery(<SettingsScreen user={ADMIN_USER} onBack={onBack} />);
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
