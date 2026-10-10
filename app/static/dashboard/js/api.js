// Thin client for the REST API. Stores tokens in localStorage and refreshes
// the access token once on a 401 before giving up.

const KEYS = { access: 'emk.access', refresh: 'emk.refresh', business: 'emk.business' };

function read(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key, value) {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* storage unavailable: session-only login */ }
}

export const session = {
  get access() { return read(KEYS.access); },
  get refresh() { return read(KEYS.refresh); },
  get business() {
    try { return JSON.parse(read(KEYS.business) || 'null'); } catch { return null; }
  },
  set(data) {
    if (data.access_token) write(KEYS.access, data.access_token);
    if (data.refresh_token) write(KEYS.refresh, data.refresh_token);
    if (data.business) write(KEYS.business, JSON.stringify(data.business));
  },
  setBusiness(business) { write(KEYS.business, JSON.stringify(business)); },
  clear() { Object.values(KEYS).forEach((k) => write(k, null)); },
  get loggedIn() { return Boolean(read(KEYS.access)); },
};

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

let refreshing = null;

async function refreshAccess() {
  if (!session.refresh) return false;
  refreshing = refreshing || fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: session.refresh }),
  }).then(async (res) => {
    if (!res.ok) return false;
    session.set(await res.json());
    return true;
  }).catch(() => false).finally(() => { refreshing = null; });
  return refreshing;
}

export function onUnauthorized(handler) { unauthorizedHandler = handler; }
let unauthorizedHandler = () => {};

// Top progress bar: shown while any request is in flight (after a short delay,
// so instant responses don't flash it).
let inFlight = 0;
let barTimer = null;
function progress(delta) {
  inFlight = Math.max(0, inFlight + delta);
  const bar = document.getElementById('progress');
  if (!bar) return;
  clearTimeout(barTimer);
  if (inFlight > 0) barTimer = setTimeout(() => bar.classList.add('active'), 120);
  else bar.classList.remove('active');
}

async function request(path, options = {}, retry = true) {
  progress(1);
  try {
    return await doRequest(path, options, retry);
  } finally {
    progress(-1);
  }
}

async function doRequest(path, { method = 'GET', body, form, raw = false, auth = true } = {}, retry = true) {
  const headers = {};
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }
  if (auth && session.access) headers.Authorization = `Bearer ${session.access}`;

  let res;
  try {
    res = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError('Network error: is the server running?', 0);
  }

  if (res.status === 401 && auth && retry && await refreshAccess()) {
    return doRequest(path, { method, body, form, raw, auth }, false);
  }
  if (res.status === 401 && auth) {
    session.clear();
    unauthorizedHandler();
    throw new ApiError('Your session has expired. Please sign in again.', 401);
  }
  if (!res.ok) {
    let data = {};
    try { data = await res.json(); } catch { /* not JSON */ }
    throw new ApiError(data.error || `Request failed (${res.status})`, res.status, data.details);
  }
  if (raw) return res;
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path, params) => request(params ? `${path}?${qs(params)}` : path),
  post: (path, body = {}) => request(path, { method: 'POST', body }),
  put: (path, body = {}) => request(path, { method: 'PUT', body }),
  del: (path) => request(path, { method: 'DELETE' }),
  upload: (path, form) => request(path, { method: 'POST', form }),
  publicPost: (path, body) => request(path, { method: 'POST', body, auth: false }),
  async download(path, body, filename) {
    const res = await request(path, { method: 'POST', body, raw: true });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: filename });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

export function qs(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  }
  return search.toString();
}

export function errorMessage(err) {
  if (!(err instanceof ApiError)) return err?.message || 'Something went wrong';
  if (!err.details) return err.message;
  if (typeof err.details === 'string') return `${err.message}: ${err.details}`;
  if (err.details.missing) return `${err.message}: ${err.details.missing.join(', ')}`;
  if (err.details.allowed) return `${err.message} (allowed: ${err.details.allowed.join(', ')})`;
  if (err.details.fields) return `${err.message}: ${err.details.fields.join(', ')}`;
  return err.message;
}
