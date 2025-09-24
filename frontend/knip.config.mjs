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
    'contexts/**/*.{ts,tsx,js,jsx}',
    'services/**/*.{ts,tsx,js,jsx}',
    'utils/**/*.{ts,tsx,js,jsx}',
    'e2e/**/*.{ts,tsx,js,jsx}',
    'playwright.config.*',
    '!**/__tests__/**',
    '!type-tests/**',
    '!types/generated/**',
  ],

  // Ignore non-app infra and flaky resolver targets
  ignore: [
    '**/__tests__/**',
    'type-tests/**',
    'types/generated/**',
    '.next/**',
    'node_modules/**',
  ],
  // Tell knip to treat module spec '@/lib/env' as provided externally
  // Older knip doesn’t support a top-level `external` field; use entry/ignore

};

export default config;
