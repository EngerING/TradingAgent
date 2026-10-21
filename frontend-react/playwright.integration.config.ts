import { readFileSync } from 'node:fs';
import { defineConfig } from '@playwright/test';
const ready = JSON.parse(readFileSync('../tmp/m014b/browser/ready.json', 'utf8')) as { origin: string };
export default defineConfig({
  testDir: './integration', fullyParallel: false, workers: 1, retries: 0, timeout: 30000,
  reporter: [['list'], ['json', { outputFile: '../artifacts/m014b/e2e.json' }], ['junit', { outputFile: '../artifacts/m014b/e2e.xml' }]],
  outputDir: '../tmp/m014b/playwright',
  use: { baseURL: ready.origin, browserName: 'chromium', viewport: { width: 1536, height: 1024 }, trace: 'off', video: 'off', screenshot: 'off' },
});
