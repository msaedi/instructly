import { dirname } from 'path';
import { fileURLToPath } from 'url';
import { FlatCompat } from '@eslint/eslintrc';
import reactRefresh from 'eslint-plugin-react-refresh';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  {
    ignores: [
      'coverage/**/*',
      '.next/**/*',
      'out/**/*',
      'node_modules/**/*',
      'playwright-report/**/*',
      'test-results/**/*',
      'next-env.d.ts',
    ],
  },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    plugins: {
      'react-refresh': reactRefresh,
    },
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
  // No additional typed-rule overrides; all pages are linted uniformly
  // React Refresh ergonomics in component and test files
  {
    files: ['components/**/*', 'features/**/*', 'app/**/*', '__tests__/**/*'],
    plugins: { 'react-refresh': reactRefresh },
    rules: {
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // Guardrails: prevent dynamic access of NEXT_PUBLIC_* in client code
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@/lib/env',
              importNames: ['env'],
              message: 'Use `@/lib/publicEnv` for NEXT_PUBLIC_* in client code. env.get() is server-only.',
            },
          ],
          // Block generated types in app/components/features; allowed only in features/shared/api/**
          patterns: ['@/types/generated/*'],
        },
      ],
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "MemberExpression[object.name='process'][property.name='env'] > MemberExpression.computed",
          message:
            'Use literal process.env.NEXT_PUBLIC_* or import from @/lib/publicEnv so Next.js can inline.',
        },
      ],
    },
  },
  // Allow generated types only in the API shim/client layer
  {
    files: ['features/shared/api/**/*'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@/lib/env',
              importNames: ['env'],
              message: 'Use `@/lib/publicEnv` for NEXT_PUBLIC_* in client code. env.get() is server-only.',
            },
          ],
          // Do NOT block generated types here (shim and API client allowed)
          patterns: [],
        },
      ],
    },
  },
  // Disable react-refresh for Next.js layout files that need to export metadata
  {
    files: ['app/layout.tsx', 'app/**/layout.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  // Disable react-refresh for hooks that export both hooks and components/utilities
  {
    files: [
      'features/shared/hooks/useAuth.tsx',
      'features/shared/hooks/usePermissions.helpers.tsx',
    ],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
  // Enforce cookies-only auth in critical surfaces (forbid localStorage token reads)
  {
    files: [
      'features/**/*',
      'components/**/*',
      'app/(admin)/**/*',
      'app/(auth)/**/*',
      'app/(public)/**/*',
      'app/dashboard/**/*',
      'app/api/proxy/**/*',
      'lib/apiBase.ts',
      'lib/betaApi.ts',
      'lib/react-query/**/*',
      'lib/api.ts',
      'lib/http.ts',
      'hooks/**/*',
    ],
    rules: {
      'no-restricted-syntax': [
        'error',
        { selector: "Identifier[name='localStorage']", message: 'Use cookie-based session; localStorage is banned.' },
        { selector: "MemberExpression[object.name='window'][property.name='localStorage']", message: 'Use cookie-based session; localStorage is banned.' },
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
    files: ['e2e/**/*', 'e2e/**/*.ts', '**/__tests__/**', '**/__tests__/**/*'],
    rules: {
      'no-console': 'off',
      'no-restricted-syntax': 'off',
    },
  },
  // Allow console in node scripts
  {
    files: ['scripts/**/*.js', 'scripts/**/*.mjs'],
    rules: {
      'no-console': 'off',
    },
  },
  // Test setup file can safely use console to filter warnings
  {
    files: ['jest.setup.js'],
    rules: {
      'no-console': 'off',
    },
  },
  // Allow console and CommonJS requires in Node/CLI files
  {
    files: ['server.js', 'scripts/**/*.js', 'jest.config.js', 'next.config.js', 'lib/logger.ts'],
    rules: {
      'no-console': 'off',
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
];

export default eslintConfig;
