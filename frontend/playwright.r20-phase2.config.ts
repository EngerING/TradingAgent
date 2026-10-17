import { defineConfig } from '@playwright/test'
import { resolve } from 'node:path'
const out = resolve(process.env.R20_UI_ARTIFACTS!)
export default defineConfig({
  testDir: './e2e',
  testMatch: ['r20-phase2.spec.ts', 'r20-configuration.spec.ts', 'r20-readiness.spec.ts'],
  fullyParallel: false, workers: 1, retries: 0, timeout: 60000,
  outputDir: resolve(out, 'browser-results'),
  reporter: [['list'], ['json', { outputFile: resolve(out, 'e2e-results.json') }]],
  use: { baseURL: 'http://127.0.0.1:5182', headless: true, viewport: { width: 1600, height: 1100 }, trace: 'off' },
})
