/**
 * Centralized API client for Meridian AI Platform.
 *
 * Auth: HttpOnly cookie `meridian_session` set by the backend on login.
 * The browser sends it automatically with every same-origin request.
 * No JWT is stored in JavaScript — XSS cannot steal it.
 *
 * For displaying user info (email, role) the login/signup response body
 * is stored as `meridian_user` in localStorage — this is non-sensitive.
 *
 * Usage:
 *   import { api } from "@/lib/api"
 *   const data = await api.get("/api/v1/evaluate/list")
 *   await api.post("/api/v1/evaluate/start", { body: { ... } })
 */

const LOGIN_PATH = "/login";

// ── User info helpers (non-sensitive display data only) ──────────────────────

export interface UserInfo {
  email: string;
  role: string;
  org_id: string;
}

export function getUserInfo(): UserInfo | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("meridian_user");
    return raw ? (JSON.parse(raw) as UserInfo) : null;
  } catch {
    return null;
  }
}

export function setUserInfo(info: UserInfo): void {
  localStorage.setItem("meridian_user", JSON.stringify(info));
}

export function clearUserInfo(): void {
  localStorage.removeItem("meridian_user");
}

export function isLoggedIn(): boolean {
  return getUserInfo() !== null;
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
  /** Called when a 401 is received — defaults to redirect to /login */
  on401?: () => void;
}

async function request<T = unknown>(
  url: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, on401, ...init } = options;

  const headers = new Headers(init.headers);

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
    credentials: "same-origin",   // sends HttpOnly cookie automatically
  });

  // Handle 401 — session expired or not logged in
  if (res.status === 401) {
    clearUserInfo();
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
      isJson && typeof data === "object" && data !== null && "detail" in data
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

  /** POST with application/x-www-form-urlencoded */
  postForm<T = unknown>(url: string, params: Record<string, string>, options?: Omit<RequestOptions, "body">) {
    return request<T>(url, {
      ...options,
      method: "POST",
      body: new URLSearchParams(params),
    });
  },
} as const;
