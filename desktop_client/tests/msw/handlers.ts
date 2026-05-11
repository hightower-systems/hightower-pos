import { http, HttpResponse } from "msw";

const API = "http://localhost";

export const okMe = {
  username: "mike",
  display_name: "Mike Hightower",
  expires_at: "2027-01-01T00:00:00",
  must_change_password: false,
};

export const okDependencies = {
  version: "0.1.0",
  terminal_id: "TERM-1",
  sentry: { reachable: true, latency_ms: 42, error: null },
  windcave: { configured: true, mock: false },
};

export const okPrintAgentStatus = {
  agent_status: "online",
  agent_version: "0.1.0",
  printer_online: true,
  last_print_at: null,
};

// Default handlers: a fresh page load presents an unauthenticated /me
// (the App should render the login screen). Individual tests override
// these via server.use(...).
export const handlers = [
  http.get(`${API}/api/auth/me`, () =>
    HttpResponse.json({ detail: { error: "not_authenticated" } }, { status: 401 }),
  ),
  // /api/till/current is polled by the RegisterScreen on mount. Default
  // to no open session so tests that don't care about till state
  // don't have to register their own handler.
  http.get(`${API}/api/till/current`, () =>
    HttpResponse.json({ status: "NONE" }),
  ),
  // Admin endpoints default to empty so screens that render them
  // don't crash when no per-test handler is registered.
  http.get(`${API}/api/admin/users`, () =>
    HttpResponse.json({ users: [] }),
  ),
  http.get(`${API}/api/till/sessions`, () =>
    HttpResponse.json({ sessions: [] }),
  ),
];
