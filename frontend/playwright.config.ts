import { defineConfig } from '@playwright/test'
export default defineConfig({ testDir: './e2e', fullyParallel: false, workers: 1, timeout: 35_000, retries: 0,
  reporter: [['list'], ['json', { outputFile: `${process.env.TRADING_UI_TEST_ARTIFACTS ?? '../artifacts/operational-ui-20261007'}/e2e-results.json` }]],
  use: { baseURL: 'http://127.0.0.1:5080', headless: true, viewport: { width: 1600, height: 1080 }, trace: 'off' },
})
