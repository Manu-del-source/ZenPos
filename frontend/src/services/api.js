import axios from 'axios';

// The API is served from the same origin under /api:
// - In production, Vercel rewrites /api/* to the backend service
//   and /api/realtime/* to the realtime service.
// - In local dev, the Vite dev server proxies /api to http://localhost:5000
//   (see vite.config.js).
const getBaseURL = () => '/api';

const api = axios.create({
  baseURL: getBaseURL(),
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
