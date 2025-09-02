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
      // Calibrate default strictness to prior behavior; critical rules enforced via targeted overrides below
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', ignoreRestSiblings: true }],
      '@next/next/no-html-link-for-pages': 'warn',
      'react/no-unescaped-entities': 'warn',
      '@typescript-eslint/ban-ts-comment': 'warn',
    },
    languageOptions: { ecmaVersion: 2022, sourceType: 'module' },
  },
  // Enforce cookies-only auth in critical surfaces (forbid localStorage token reads)
  {
    files: [
      'features/**/*',
      'components/**/*',
      'app/(admin)/**/*',
      'app/api/proxy/**/*',
      'lib/apiBase.ts',
      'lib/betaApi.ts',
      'lib/react-query/**/*',
    ],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: "CallExpression[callee.object.name='localStorage'][callee.property.name='getItem'][arguments.0.value='access_token']",
          message: 'Auth must use cookies; localStorage access_token is forbidden.',
        },
        {
          selector: "CallExpression[callee.object.name='localStorage'][callee.property.name='getItem'][arguments.0.value='token']",
          message: 'Auth must use cookies; localStorage token is forbidden.',
        },
        {
          selector: "CallExpression[callee.object.name='localStorage'][callee.property.name='setItem'][arguments.0.value='access_token']",
          message: 'Do not set access_token in localStorage.',
        },
        {
          selector: "CallExpression[callee.object.name='localStorage'][callee.property.name='removeItem'][arguments.0.value='access_token']",
          message: 'Do not manage access_token in localStorage.',
        },
      ],
    },
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
