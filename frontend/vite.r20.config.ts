import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
export default defineConfig({plugins:[vue()],build:{outDir:process.env.R20_LAB_BUILD_DIR??'../artifacts/aggressive-growth-r20-20261010/r20-v2-api-dashboard-20261012/ui-dist',rollupOptions:{input:fileURLToPath(new URL('./r20-config.html',import.meta.url))}}})
