// Thin fetch wrapper for the InternAlign API.
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const TOKEN_KEY = "token";
const USER_KEY = "user";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export const session = {
  token: () => localStorage.getItem(TOKEN_KEY),
  user: () => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY));
    } catch {
      return null;
    }
  },
  save: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

let onUnauthorized = () => {};
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

// FastAPI returns `detail` as a string (our errors) or a list (validation errors).
function messageFrom(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((item) => String(item.msg || "").replace(/^Value error, /, ""))
      .filter(Boolean)
      .join(". ");
  }
  return fallback;
}

/**
 * api("/matches")
 * api("/login", { method: "POST", json: { email, password } })
 * api("/resume", { method: "POST", form: formData })
 */
export async function api(path, { method = "GET", json, form, auth = true } = {}) {
  const headers = {};
  const token = session.token();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  if (json) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: json ? JSON.stringify(json) : form,
    });
  } catch {
    throw new ApiError(`Can't reach the server at ${API_URL}. Is the backend running?`, 0);
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    // An expired session on a protected route; login failures also return 401, so skip those.
    if (response.status === 401 && auth) onUnauthorized();
    throw new ApiError(messageFrom(data?.detail, "Something went wrong."), response.status);
  }
  return data;
}
