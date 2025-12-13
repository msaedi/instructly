import { defineConfig, devices } from '@playwright/test';
import { env } from './lib/env';

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// import dotenv from 'dotenv';
// import path from 'path';
// dotenv.config({ path: path.resolve(__dirname, '.env') });

const isCI = env.isCI();
const skipWebServer = Boolean(process.env['SKIP_WEB_SERVER']);

const getCleanProcessEnv = (): Record<string, string> => {
  const cleaned: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (typeof value === 'string') {
      cleaned[key] = value;
    }
  }
  return cleaned;
};

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  globalSetup: './playwright.global-setup.ts',
  testDir: './e2e',
  /* Run tests in files in parallel */
  fullyParallel: !isCI, // Disable parallel in CI
  ...(isCI ? {} : { workers: 2 }),
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: isCI,
  /* Retry on CI only - REDUCED to avoid 20 minute runs */
  retries: isCI ? 1 : 0,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: isCI
    ? [
        ['list'],
        ['junit', { outputFile: 'test-results/junit.xml' }],
        ['html', { outputFolder: 'playwright-report', open: 'never' }]
      ]
    : [['html', { open: 'on-failure' }]],
  /* Timeout per test */
  timeout: 60_000,
  /* Expect timeout for assertions */
  expect: {
    timeout: 10_000,
  },
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: env.getOrDefault('PLAYWRIGHT_BASE_URL', 'http://localhost:3100'),

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: isCI ? 'on-first-retry' : 'retain-on-failure',

    /* Screenshot on failure */
    screenshot: 'only-on-failure',

    /* Video on failure - capture on retry in CI for better debugging */
    video: isCI ? 'on-first-retry' : 'retain-on-failure',

    /* Additional options for stability */
    actionTimeout: 30_000,
    navigationTimeout: 30_000,
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'instructor',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.storage/instructor.json' },
    },
    {
      name: 'admin',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.storage/admin.json' },
    },
    {
      name: 'anon',
      use: { ...devices['Desktop Chrome'], storageState: undefined },
    },

    // Uncomment to test on other browsers
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
  ],

  /* Run your local dev server before starting the tests */
  ...(!env.isCI() && !skipWebServer && {
    webServer: {
      command: 'npm run dev:test',
      url: 'http://localhost:3100',
      reuseExistingServer: !env.get('CI'),
      timeout: 120 * 1000,
      // IMPORTANT: Pass environment variables to the Next.js process
      env: {
        ...getCleanProcessEnv(),
        NEXT_PUBLIC_API_BASE: 'http://localhost:8000',
        NEXT_PUBLIC_USE_PROXY: 'false',
        NEXT_PUBLIC_APP_ENV: 'e2e',
        NODE_ENV: 'development',
      },
    },
  }),
});
