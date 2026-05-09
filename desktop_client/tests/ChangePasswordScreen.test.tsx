import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { ChangePasswordScreen } from "../src/screens/ChangePasswordScreen";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

const USER = {
  username: "admin",
  display_name: "Administrator",
  expires_at: "2027-01-01T00:00:00",
  must_change_password: true,
};

describe("<ChangePasswordScreen>", () => {
  it("renders the three password fields and a disabled submit on mount", () => {
    renderWithQuery(
      <ChangePasswordScreen
        user={USER}
        onChanged={() => {}}
        onSignedOut={() => {}}
      />,
    );
    expect(screen.getByLabelText(/^current password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^new password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^confirm new password$/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save new password/i }),
    ).toBeDisabled();
  });

  it("disables save while new and confirm don't match", async () => {
    renderWithQuery(
      <ChangePasswordScreen
        user={USER}
        onChanged={() => {}}
        onSignedOut={() => {}}
      />,
    );
    await userEvent.type(screen.getByLabelText(/^current password$/i), "admin");
    await userEvent.type(screen.getByLabelText(/^new password$/i), "abc12345");
    await userEvent.type(screen.getByLabelText(/^confirm new password$/i), "different");
    expect(
      screen.getByRole("button", { name: /save new password/i }),
    ).toBeDisabled();
    expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it("calls onChanged with the updated user on a successful change", async () => {
    server.use(
      http.post(`${API}/api/auth/change-password`, () =>
        HttpResponse.json({
          ...USER,
          must_change_password: false,
        }),
      ),
    );
    const onChanged = vi.fn();
    renderWithQuery(
      <ChangePasswordScreen
        user={USER}
        onChanged={onChanged}
        onSignedOut={() => {}}
      />,
    );

    await userEvent.type(screen.getByLabelText(/^current password$/i), "admin");
    await userEvent.type(screen.getByLabelText(/^new password$/i), "abc12345");
    await userEvent.type(screen.getByLabelText(/^confirm new password$/i), "abc12345");
    await userEvent.click(
      screen.getByRole("button", { name: /save new password/i }),
    );

    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(onChanged.mock.calls[0][0].must_change_password).toBe(false);
  });

  it("renders the friendly invalid_credentials message on 401", async () => {
    server.use(
      http.post(`${API}/api/auth/change-password`, () =>
        HttpResponse.json(
          { detail: { error: "invalid_credentials" } },
          { status: 401 },
        ),
      ),
    );
    renderWithQuery(
      <ChangePasswordScreen
        user={USER}
        onChanged={() => {}}
        onSignedOut={() => {}}
      />,
    );

    await userEvent.type(screen.getByLabelText(/^current password$/i), "wrong");
    await userEvent.type(screen.getByLabelText(/^new password$/i), "abc12345");
    await userEvent.type(screen.getByLabelText(/^confirm new password$/i), "abc12345");
    await userEvent.click(
      screen.getByRole("button", { name: /save new password/i }),
    );

    expect(
      await screen.findByText(/current password is wrong/i),
    ).toBeInTheDocument();
  });

  it("renders the new_password_must_differ message on 400", async () => {
    server.use(
      http.post(`${API}/api/auth/change-password`, () =>
        HttpResponse.json(
          { detail: { error: "new_password_must_differ" } },
          { status: 400 },
        ),
      ),
    );
    renderWithQuery(
      <ChangePasswordScreen
        user={USER}
        onChanged={() => {}}
        onSignedOut={() => {}}
      />,
    );

    await userEvent.type(screen.getByLabelText(/^current password$/i), "admin");
    await userEvent.type(screen.getByLabelText(/^new password$/i), "admin");
    await userEvent.type(screen.getByLabelText(/^confirm new password$/i), "admin");
    await userEvent.click(
      screen.getByRole("button", { name: /save new password/i }),
    );

    expect(
      await screen.findByText(/different from the current/i),
    ).toBeInTheDocument();
  });

  it("Sign out fires the logout flow", async () => {
    server.use(
      http.post(`${API}/api/auth/logout`, () =>
        HttpResponse.json({ ok: true }),
      ),
    );
    const onSignedOut = vi.fn();
    renderWithQuery(
      <ChangePasswordScreen
        user={USER}
        onChanged={() => {}}
        onSignedOut={onSignedOut}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));
    await waitFor(() => expect(onSignedOut).toHaveBeenCalledOnce());
  });
});
