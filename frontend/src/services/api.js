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
  if (error?.response?.status === 401) return 'Invalid username or password.';
  if (error?.response?.status === 403) return 'Your account does not have permission to do that.';
  if (error?.response?.status) return `The server returned HTTP ${error.response.status}.`;
  if (error?.message === 'Network Error') return 'The server could not be reached.';
  return fallback;
};

export default api;
