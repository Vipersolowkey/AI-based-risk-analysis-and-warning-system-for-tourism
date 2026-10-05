// Keep relative URLs in local development so Vite's proxy is used. In a
// production build, point this at the deployed FastAPI service. This keeps the
// frontend independent from short-lived Railway/Render domains.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

function _url(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalizedPath}`;
}

async function _handleResponse(r) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg =
      data?.detail ||
      data?.message ||
      data?.error ||
      `Server returned ${r.status} ${r.statusText}`;
    throw new Error(msg);
  }
  return data;
}

function _networkError(networkErr) {
  const server = API_BASE || "backend local (http://127.0.0.1:8000)";
  return new Error(
    `Không kết nối được server ${server}. Vui lòng kiểm tra backend đang chạy (${networkErr.message}).`
  );
}

export async function apiGet(path, token) {
  let r;
  try {
    r = await fetch(_url(path), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch (networkErr) {
    throw _networkError(networkErr);
  }
  return _handleResponse(r);
}

export async function apiPost(path, body, token) {
  let r;
  try {
    r = await fetch(_url(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body || {}),
    });
  } catch (networkErr) {
    throw _networkError(networkErr);
  }
  return _handleResponse(r);
}

export async function apiDelete(path, token) {
  let r;
  try {
    r = await fetch(_url(path), {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch (networkErr) {
    throw _networkError(networkErr);
  }
  return _handleResponse(r);
}
