import { dirname } from 'path';
import { fileURLToPath } from 'url';
import { FlatCompat } from '@eslint/eslintrc';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  {
    ignores: [
      'scripts/**/*',
      '**/*.js',
      '.next/**/*',
      'out/**/*',
      'node_modules/**/*',
      'server.js',
      'jest.config.js',
      'jest.setup.js',
    ],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      // Ban console usage in app code; prefer our logger. Allow warn/error in server.js and tests via overrides.
      'no-console': ['error'],
    },
    languageOptions: { ecmaVersion: 2022, sourceType: 'module' },
  },
  // Allow console in e2e/tests and mock fixtures
  {
    files: ['e2e/**/*', '__tests__/**/*', 'e2e/**/*.ts'],
    rules: {
      'no-console': 'off',
    },
  },
  // Allow console in server.js and logger implementation
  {
    files: ['server.js', 'lib/logger.ts'],
    rules: {
      'no-console': 'off',
    },
  },
];

export default eslintConfig;
