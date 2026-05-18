/**
 * Centralized API client for Meridian AI Platform.
 *
 * All requests to /api/v1/* go through here.
 * Handles: auth token injection, 401 redirect, JSON parsing, error normalization.
 *
 * Usage:
 *   import { api } from "@/lib/api"
 *   const data = await api.get("/api/v1/evaluate/list")
 *   const result = await api.post("/api/v1/evaluate/start", { body: formData })
 */

const LOGIN_PATH = "/login";

// ── Token helpers ────────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

export function setToken(token: string): void {
  localStorage.setItem("access_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("access_token");
}

export function getTokenPayload(): Record<string, unknown> | null {
  const token = getToken();
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split(".")[1]));
  } catch {
    return null;
  }
}

// ── API error ────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Core request ─────────────────────────────────────────────────────────────

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip attaching the Authorization header (used for login/signup) */
  skipAuth?: boolean;
  /** Called when a 401 is received — defaults to window.location redirect */
  on401?: () => void;
}

async function request<T = unknown>(
  url: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, skipAuth, on401, ...init } = options;

  const headers = new Headers(init.headers);

  // Attach auth token unless explicitly skipped
  if (!skipAuth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  // Serialize body
  let serializedBody: BodyInit | undefined;
  if (body instanceof FormData || body instanceof URLSearchParams) {
    serializedBody = body as BodyInit;
  } else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    serializedBody = JSON.stringify(body);
  }

  const res = await fetch(url, {
    ...init,
    headers,
    body: serializedBody,
  });

  // Handle 401 — redirect to login
  if (res.status === 401) {
    clearToken();
    if (on401) {
      on401();
    } else if (typeof window !== "undefined") {
      window.location.href = LOGIN_PATH;
    }
    throw new ApiError(401, "Session expired — please log in again.");
  }

  // Parse response
  const contentType = res.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const data = isJson ? await res.json() : await res.text();

  if (!res.ok) {
    const message =
      (isJson && typeof data === "object" && data !== null && "detail" in data)
        ? String((data as { detail: unknown }).detail)
        : `Request failed (${res.status})`;
    throw new ApiError(res.status, message, data);
  }

  return data as T;
}

// ── Typed convenience methods ─────────────────────────────────────────────────

export const api = {
  get<T = unknown>(url: string, options?: Omit<RequestOptions, "body" | "method">) {
    return request<T>(url, { ...options, method: "GET" });
  },

  post<T = unknown>(url: string, options?: RequestOptions) {
    return request<T>(url, { ...options, method: "POST" });
  },

  put<T = unknown>(url: string, options?: RequestOptions) {
    return request<T>(url, { ...options, method: "PUT" });
  },

  patch<T = unknown>(url: string, options?: RequestOptions) {
    return request<T>(url, { ...options, method: "PATCH" });
  },

  delete<T = unknown>(url: string, options?: Omit<RequestOptions, "body" | "method">) {
    return request<T>(url, { ...options, method: "DELETE" });
  },

  /** POST with application/x-www-form-urlencoded — used for OAuth2 token endpoint */
  postForm<T = unknown>(url: string, params: Record<string, string>, options?: Omit<RequestOptions, "body">) {
    return request<T>(url, {
      ...options,
      method: "POST",
      body: new URLSearchParams(params),
    });
  },
} as const;
