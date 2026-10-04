import axios from 'axios';

// Production and local builds use the Django REST API under /api/v2.
// Vercel rewrites /api/v2/* to the Render Django service.
const getBaseURL = () => '/api/v2';

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
