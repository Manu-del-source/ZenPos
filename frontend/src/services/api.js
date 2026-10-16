import axios from 'axios';

/**
 * Django REST API is versioned under /api/v2. In production, Vercel forwards
 * same-origin /api requests to the Render backend. VITE_API_BASE_URL remains
 * available for local development or an explicitly configured API origin.
 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v2').replace(/\/$/, '');

export const SESSION_KEYS = ['token', 'refreshToken', 'user'];

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { Accept: 'application/json' },
});

// Keep simultaneous 401 responses from rotating the same refresh token more
// than once. SimpleJWT rotates refresh tokens and blacklists the previous one.
let refreshInFlight = null;

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const clearSession = () => {
  SESSION_KEYS.forEach((key) => localStorage.removeItem(key));
  localStorage.removeItem('pos.branch');
  sessionStorage.clear();
};

export const endSession = () => {
  clearSession();
  if (window.location.pathname !== '/login') window.location.href = '/login';
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;
    const url = original?.url || '';

    // Never refresh a failed login, refresh, or logout request, and never
    // retry the same API request more than once.
    const isAuthEndpoint = /\/auth\/(login|refresh|logout)\//.test(url);
    if (status !== 401 || !original || original._authRetry || isAuthEndpoint) {
      return Promise.reject(error);
    }

    const refresh = localStorage.getItem('refreshToken');
    if (!refresh) {
      endSession();
      return Promise.reject(error);
    }

    original._authRetry = true;

    try {
      if (!refreshInFlight) {
        refreshInFlight = axios
          .post(`${API_BASE_URL}/auth/refresh/`, { refresh }, {
            headers: { Accept: 'application/json' },
          })
          .then(({ data }) => {
            if (!data?.access) {
              throw new Error('The refresh response did not include an access token.');
            }
            localStorage.setItem('token', data.access);
            // ROTATE_REFRESH_TOKENS is enabled on the API. Persist the new
            // refresh token or the next refresh will fail as blacklisted.
            if (data.refresh) localStorage.setItem('refreshToken', data.refresh);
            return data.access;
          })
          .finally(() => {
            refreshInFlight = null;
          });
      }

      const access = await refreshInFlight;
      original.headers = original.headers || {};
      original.headers.Authorization = `Bearer ${access}`;
      return api(original);
    } catch (refreshError) {
      endSession();
      return Promise.reject(refreshError);
    }
  },
);

export const logout = async () => {
  const refresh = localStorage.getItem('refreshToken');
  try {
    await api.post('/auth/logout/', refresh ? { refresh } : {});
  } catch (error) {
    if (![401, 403, 404, 405].includes(error?.response?.status)) {
      console.warn('Server-side logout failed; clearing the local session anyway.');
    }
  }
  endSession();
};

/** Convert API errors into readable messages without hiding HTTP failures. */
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
  if (error?.response?.status === 401) return 'Your session is invalid or has expired. Please sign in again.';
  if (error?.response?.status === 403) return 'Your account does not have permission to do that.';
  if (error?.response?.status) return `The server returned HTTP ${error.response.status}.`;
  if (error?.message === 'Network Error') return 'The server could not be reached.';
  return fallback;
};

export default api;
