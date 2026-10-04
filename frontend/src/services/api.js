import axios from 'axios';

const getBaseURL = () => 'https://zenpos-ef02.onrender.com/api/v2';

const api = axios.create({
  baseURL: getBaseURL(),
});

let refreshPromise = null;

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

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
      refreshPromise ||= axios.post(`${getBaseURL()}/auth/refresh/`, {
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
      localStorage.removeItem('token');
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('user');

      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }

      return Promise.reject(refreshError);
    }
  },
);

export default api;
