/**
 * Fetch wrapper pro komunikaci s FastAPI backendem.
 *
 * Cookies jsou httpOnly a browser je posílá automaticky díky Next.js proxy
 * (same-origin). credentials: 'include' není potřeba – jsme na stejném originu.
 *
 * 401 → redirect na /login (access token expiroval, uživatel se musí znovu přihlásit)
 *
 * CSRF (double-submit cookie): backend setuje non-httpOnly `csrf_token` cookie
 * při loginu/registraci/refreshi. Pro state-changing requesty (POST/PUT/PATCH/
 * DELETE) ho musíme přiložit jako X-CSRF-Token header. Cookie přečteme z
 * document.cookie.
 */

const BASE = "/api/v1";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail);
  }
}

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body) headers["Content-Type"] = "application/json";

  if (!SAFE_METHODS.has(method)) {
    const csrf = getCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });

  if (res.status === 401) {
    // Token expiroval nebo chybí → přesměruj na přihlášení
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "Neautorizovaný přístup");
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (typeof err.detail === "string") detail = err.detail;
      else if (Array.isArray(err.detail)) detail = err.detail.map((e: { msg: string }) => e.msg).join(", ");
    } catch {}
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T = void>(path: string) => request<T>("DELETE", path),
};

/**
 * Multipart upload. Pro importní flow (CSV → /employees/import).
 * Nepřidává Content-Type — browser nastaví s boundary automaticky.
 */
export async function uploadFile<T>(
  path: string,
  file: File,
  fieldName: string = "file",
): Promise<T> {
  const formData = new FormData();
  formData.append(fieldName, file);

  const headers: Record<string, string> = {};
  const csrf = getCsrfToken();
  if (csrf) headers["X-CSRF-Token"] = csrf;

  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    body: formData,
    credentials: "same-origin",
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Neautorizovaný přístup");
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      if (typeof err.detail === "string") detail = err.detail;
      else if (Array.isArray(err.detail)) detail = err.detail.map((e: { msg: string }) => e.msg).join(", ");
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string) {
  return api.post("/auth/login", { email, password });
}

export async function logout() {
  await api.post("/auth/logout");
  window.location.href = "/login";
}

export async function getMe() {
  return api.get("/auth/me");
}
