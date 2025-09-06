// knip v5.63.1 configuration (ESM)
// Programmatic config to reliably ignore Playwright/e2e infra and honor TS paths

/** @type {import('knip').KnipConfig} */
const config = {
  // Ensure TS path aliases are respected
  project: ['tsconfig.json'],

  // Limit analysis to app code entry points with explicit excludes
  entry: [
    'app/**/*.{ts,tsx,js,jsx}',
    'components/**/*.{ts,tsx,js,jsx}',
    'features/**/*.{ts,tsx,js,jsx}',
    'hooks/**/*.{ts,tsx,js,jsx}',
    'lib/**/*.{ts,tsx,js,jsx}',
    '!playwright.config.ts',
    '!e2e/**',
    '!**/__tests__/**',
    '!type-tests/**',
    '!types/generated/**',
  ],

  // Ignore non-app infra and flaky resolver targets
  ignore: [
    'playwright.config.ts',
    'e2e/**',
    '**/__tests__/**',
    'type-tests/**',
    'types/generated/**',
    '.next/**',
    'node_modules/**',
  ],

  external: ['@/lib/env'],

};

export default config;
