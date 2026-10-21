import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, retries: 0, timeout: 30_000,
  reporter: [['list'], ['junit', { outputFile: '../artifacts/m014a/e2e.xml' }], ['json', { outputFile: '../artifacts/m014a/e2e.json' }]],
  outputDir: '../artifacts/m014a/playwright',
  use: { browserName: 'chromium', viewport: { width: 1536, height: 1024 }, trace: 'off', video: 'off', screenshot: 'off' },
  webServer: [
    { command: 'npm run dev', url: 'http://localhost:3000', reuseExistingServer: false },
    { command: 'npm run preview', url: 'http://localhost:3001', reuseExistingServer: false },
  ],
});
