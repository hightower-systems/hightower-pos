export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string | null,
    public readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : code ?? `HTTP ${status}`);
    this.name = "ApiError";
  }
}

interface DetailWithError {
  error?: string;
}

interface BodyWithDetail {
  detail?: DetailWithError | string;
}

function extractErrorCode(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const detail = (body as BodyWithDetail).detail;
  if (detail && typeof detail === "object" && "error" in detail) {
    return (detail as DetailWithError).error ?? null;
  }
  return null;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers,
  });
  let body: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, extractErrorCode(body), body);
  }
  return body as T;
}
