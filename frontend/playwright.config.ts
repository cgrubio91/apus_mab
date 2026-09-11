import { defineConfig, devices } from '@playwright/test';

// Smoke E2E: flujos críticos sin backend real (se mockean las respuestas API).
// Correr con: npm run test:e2e  (requiere `npx playwright install chromium` una vez)
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: 'http://localhost:4200',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npx ng serve --port 4200',
    url: 'http://localhost:4200/login',
    reuseExistingServer: !process.env.CI,
    timeout: 180 * 1000,
  },
});
