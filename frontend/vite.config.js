import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The Django API is served by the platform in deployment (see `vercel.json`)
// and by `manage.py runserver` in development. `VITE_DEV_API_TARGET` overrides
// the dev target for a remote API; the default matches the documented runbook.
const devApiTarget = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  // The pure modules (the offline queue and friends) are tested with vitest
  // in a plain node environment: no DOM, no network — the storage is
  // injected, which is the whole point of keeping them browser-free.
  test: {
    environment: 'node',
    include: ['src/**/*.test.js'],
  },
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: {
      '/api': {
        target: devApiTarget,
        changeOrigin: true,
      },
      // Receipt printing loads no remote assets, but the callback endpoints are
      // excluded on purpose: providers call the API host directly.
    },
  },
});
