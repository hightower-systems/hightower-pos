import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ApiError, api } from "../src/api/client";
import { server } from "./msw/server";

const API = "http://localhost";

describe("api()", () => {
  it("parses JSON response on 200", async () => {
    server.use(
      http.get(`${API}/api/test`, () => HttpResponse.json({ hello: "world" })),
    );
    const body = await api<{ hello: string }>("/api/test");
    expect(body).toEqual({ hello: "world" });
  });

  it("throws ApiError with code on 4xx with FastAPI-style detail", async () => {
    server.use(
      http.get(`${API}/api/protected`, () =>
        HttpResponse.json(
          { detail: { error: "not_authenticated" } },
          { status: 401 },
        ),
      ),
    );
    await expect(api("/api/protected")).rejects.toMatchObject({
      status: 401,
      code: "not_authenticated",
    });
  });

  it("throws ApiError with code=null when body has no error field", async () => {
    server.use(
      http.get(`${API}/api/x`, () => HttpResponse.json({ foo: 1 }, { status: 500 })),
    );
    try {
      await api("/api/x");
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(500);
      expect(apiErr.code).toBeNull();
    }
  });

  it("sends Content-Type: application/json on requests with a body", async () => {
    let seenContentType: string | null = null;
    server.use(
      http.post(`${API}/api/echo`, async ({ request }) => {
        seenContentType = request.headers.get("content-type");
        return HttpResponse.json({ ok: true });
      }),
    );
    await api("/api/echo", { method: "POST", body: JSON.stringify({ a: 1 }) });
    expect(seenContentType).toContain("application/json");
  });
});
