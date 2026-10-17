import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: { host: '127.0.0.1', allowedHosts: ['127.0.0.1'], proxy: {
    '/api': { target: 'http://127.0.0.1:5080', changeOrigin: true },
    '/hubs': { target: 'http://127.0.0.1:5080', changeOrigin: true, ws: true },
  } },
  build: { sourcemap: false, rollupOptions: { output: { manualChunks(id) { if (id.includes('/node_modules/@microsoft/signalr/')) return 'transport'; if (id.includes('/node_modules/zod/')) return 'contracts'; if (/node_modules\/(?:@vue|vue|pinia|vue-router)\//.test(id)) return 'vue' } } } },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts'], restoreMocks: true },
})
