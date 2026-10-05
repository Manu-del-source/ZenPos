import axios from 'axios';

/**
 * The API base URL.
 *
 * Relative by default, so the browser talks to the origin it was served from
 * and the deployment platform proxies `/api/v2` to Django (see `vercel.json`).
 * Hard-coding the Render host here coupled the bundle to one environment,
 * made every request cross-origin, and meant CORS had to be reconfigured
 * wherever the API moved. `VITE_API_BASE_URL` is an escape hatch for running
 * a build against a different API — it is a public value by definition, so it
 * must never hold a secret.
 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v2').replace(/\/$/, '');

/** Session keys in one place, so "signed out" always means the same thing. */
export const SESSION_KEYS = ['token', 'refreshToken', 'user'];

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { Accept: 'application/json' },
});

let refreshPromise = null;

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** Clear the session and send the user to the login screen exactly once. */
export const clearSession = () => {
  SESSION_KEYS.forEach((key) => localStorage.removeItem(key));
  localStorage.removeItem('pos.branch');
  sessionStorage.clear();
};

export const endSession = () => {
  clearSession();
  if (window.location.pathname !== '/login') {
    window.location.href = '/login';
  }
};

/**
 * End the session server-side as well as locally: the refresh token is
 * blacklisted by the API, so a token copied off the device cannot be replayed
 * after the cashier signs out. The local session is always cleared, even when
 * the API cannot be reached, or a network blip would leave the till signed in.
 */
export const logout = async () => {
  const refresh = localStorage.getItem('refreshToken');
  try {
    await api.post('/auth/logout/', { refresh });
  } catch (error) {
    if (![401, 403].includes(error?.response?.status)) {
      console.warn('Server-side logout failed; clearing the local session anyway.');
    }
  }
  endSession();
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    const refreshToken = localStorage.getItem('refreshToken');

    if (
      status !== 401 ||
      !refreshToken ||
      original?._retry ||
      original?.url?.includes('/auth/login/') ||
      original?.url?.includes('/auth/refresh/')
    ) {
      return Promise.reject(error);
    }

    original._retry = true;

    try {
      // One refresh for a burst of 401s: without this, five parallel requests
      // would each rotate the token and four of them would be rejected.
      refreshPromise ||= axios.post(`${API_BASE_URL}/auth/refresh/`, {
        refresh: refreshToken,
      });

      const { data } = await refreshPromise;
      refreshPromise = null;

      if (!data?.access) {
        throw new Error('Refresh response did not include an access token.');
      }

      localStorage.setItem('token', data.access);
      if (data.refresh) {
        localStorage.setItem('refreshToken', data.refresh);
      }

      original.headers = original.headers || {};
      original.headers.Authorization = `Bearer ${data.access}`;
      return api(original);
    } catch (refreshError) {
      refreshPromise = null;
      endSession();
      return Promise.reject(refreshError);
    }
  },
);

/** Read the first human-readable message out of a DRF error response. */
export const apiError = (error, fallback = 'Something went wrong.') => {
  const data = error?.response?.data;
  if (typeof data === 'string' && data) return data;
  if (typeof data?.detail === 'string') return data.detail;
  if (data && typeof data === 'object') {
    for (const value of Object.values(data)) {
      if (Array.isArray(value) && value.length) return String(value[0]);
      if (typeof value === 'string') return value;
    }
  }
  if (error?.response?.status === 401) return 'Your session has expired. Sign in again.';
  if (error?.response?.status === 403) return 'Your account does not have permission to do that.';
  if (error?.message === 'Network Error') return 'The server could not be reached.';
  return fallback;
};

export default api;
