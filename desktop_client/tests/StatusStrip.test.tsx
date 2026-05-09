import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { StatusStrip } from "../src/components/StatusStrip";
import { server } from "./msw/server";
import { okDependencies, okPrintAgentStatus } from "./msw/handlers";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

describe("<StatusStrip>", () => {
  it("renders all green dots when every dependency is up", async () => {
    server.use(
      http.get(`${API}/api/health/dependencies`, () =>
        HttpResponse.json(okDependencies),
      ),
      http.get(`${API}/print-agent/status`, () =>
        HttpResponse.json(okPrintAgentStatus),
      ),
    );

    renderWithQuery(
      <StatusStrip
        cashier={{ display_name: "Mike Hightower" }}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Sentry: online")).toBeInTheDocument();
      expect(screen.getByLabelText("Windcave: online")).toBeInTheDocument();
      expect(screen.getByLabelText("Print Agent: online")).toBeInTheDocument();
    });
  });

  it("flips Sentry red when reachable=false", async () => {
    server.use(
      http.get(`${API}/api/health/dependencies`, () =>
        HttpResponse.json({
          ...okDependencies,
          sentry: { reachable: false, latency_ms: null, error: "5xx" },
        }),
      ),
      http.get(`${API}/print-agent/status`, () =>
        HttpResponse.json(okPrintAgentStatus),
      ),
    );

    renderWithQuery(
      <StatusStrip
        cashier={{ display_name: "Mike Hightower" }}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Sentry: offline")).toBeInTheDocument();
    });
  });

  it("flips Print Agent red when its /status endpoint errors", async () => {
    server.use(
      http.get(`${API}/api/health/dependencies`, () =>
        HttpResponse.json(okDependencies),
      ),
      http.get(`${API}/print-agent/status`, () =>
        HttpResponse.json({ error: "boom" }, { status: 503 }),
      ),
    );

    renderWithQuery(
      <StatusStrip
        cashier={{ display_name: "Mike Hightower" }}
        onSignOut={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Print Agent: unknown")).toBeInTheDocument();
    });
  });

  it("renders the cashier display name and the terminal id", async () => {
    server.use(
      http.get(`${API}/api/health/dependencies`, () =>
        HttpResponse.json(okDependencies),
      ),
      http.get(`${API}/print-agent/status`, () =>
        HttpResponse.json(okPrintAgentStatus),
      ),
    );

    renderWithQuery(
      <StatusStrip
        cashier={{ display_name: "Mike Hightower" }}
        onSignOut={() => {}}
      />,
    );

    expect(screen.getByText("Mike Hightower")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("TERM-1")).toBeInTheDocument(),
    );
  });
});
