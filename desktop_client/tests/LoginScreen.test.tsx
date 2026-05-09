import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { LoginScreen } from "../src/screens/LoginScreen";
import { server } from "./msw/server";
import { okMe } from "./msw/handlers";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

describe("<LoginScreen>", () => {
  it("renders the form fields and submit button", () => {
    renderWithQuery(<LoginScreen onSuccess={() => {}} />);
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("calls onSuccess after a 200 login", async () => {
    server.use(http.post(`${API}/api/auth/login`, () => HttpResponse.json(okMe)));
    const onSuccess = vi.fn();
    renderWithQuery(<LoginScreen onSuccess={onSuccess} />);

    await userEvent.type(screen.getByLabelText(/username/i), "mike");
    await userEvent.type(screen.getByLabelText(/password/i), "supersecret");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
  });

  it("renders the friendly invalid_credentials message on 401", async () => {
    server.use(
      http.post(`${API}/api/auth/login`, () =>
        HttpResponse.json(
          { detail: { error: "invalid_credentials" } },
          { status: 401 },
        ),
      ),
    );
    renderWithQuery(<LoginScreen onSuccess={() => {}} />);

    await userEvent.type(screen.getByLabelText(/username/i), "mike");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/wrong username or password/i),
    ).toBeInTheDocument();
  });

  it("renders a generic error message on 500", async () => {
    server.use(
      http.post(`${API}/api/auth/login`, () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    renderWithQuery(<LoginScreen onSuccess={() => {}} />);

    await userEvent.type(screen.getByLabelText(/username/i), "mike");
    await userEvent.type(screen.getByLabelText(/password/i), "x");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/could not reach the pos service/i),
    ).toBeInTheDocument();
  });
});
