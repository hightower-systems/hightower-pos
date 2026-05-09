import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import App from "../src/App";
import { server } from "./msw/server";
import { okDependencies, okMe, okPrintAgentStatus } from "./msw/handlers";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

describe("<App>", () => {
  it("shows the LoginScreen when /api/auth/me returns 401", async () => {
    renderWithQuery(<App />);
    expect(
      await screen.findByRole("heading", { name: /hightower pos/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
  });

  it("shows the RegisterScreen when /api/auth/me returns a valid user", async () => {
    server.use(
      http.get(`${API}/api/auth/me`, () => HttpResponse.json(okMe)),
      http.get(`${API}/api/health/dependencies`, () =>
        HttpResponse.json(okDependencies),
      ),
      http.get(`${API}/print-agent/status`, () =>
        HttpResponse.json(okPrintAgentStatus),
      ),
    );
    renderWithQuery(<App />);
    await waitFor(() => {
      expect(screen.getByText("Mike Hightower")).toBeInTheDocument();
    });
    expect(screen.getByText(/cart is empty/i)).toBeInTheDocument();
  });

  it("routes a must_change_password user to the change-password screen with the form", async () => {
    server.use(
      http.get(`${API}/api/auth/me`, () =>
        HttpResponse.json({ ...okMe, must_change_password: true }),
      ),
    );
    renderWithQuery(<App />);
    await waitFor(() => {
      expect(
        screen.getByText(/password change required/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/^current password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^new password$/i)).toBeInTheDocument();
    expect(
      screen.getByLabelText(/^confirm new password$/i),
    ).toBeInTheDocument();
  });
});
