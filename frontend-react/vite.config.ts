import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const headers = {
  'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff',
  'Cache-Control': 'no-store',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
};
export default defineConfig({
  plugins: [react()],
  server: { host: 'localhost', port: 3000, strictPort: true, headers },
  preview: { host: 'localhost', port: 3001, strictPort: true, headers: {
    ...headers,
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  } },
  build: { sourcemap: false },
});
