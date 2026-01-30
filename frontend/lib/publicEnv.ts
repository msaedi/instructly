/**
 * Public environment variables for Next.js
 *
 * IMPORTANT: This file uses literal process.env.NEXT_PUBLIC_* access
 * so that Next.js can inline these values at build time.
 *
 * DO NOT use dynamic access like process.env[key] or env.get(key) here!
 */

const RAW_API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';
const RAW_APP_ENV = process.env.NEXT_PUBLIC_APP_ENV;
const RAW_PUBLIC_ENV = process.env.NEXT_PUBLIC_ENV;
const RAW_USE_PROXY = process.env.NEXT_PUBLIC_USE_PROXY ?? '';
const RAW_APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000';
const RAW_SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN ?? '';

// Required environment variables
export const API_BASE = RAW_API_BASE || undefined;

// Optional environment variables with defaults
export const APP_ENV = RAW_APP_ENV ?? 'local';
export const PUBLIC_ENV = RAW_PUBLIC_ENV ?? '';
export const USE_PROXY = RAW_USE_PROXY === 'true';
export const APP_URL = RAW_APP_URL;
export const SENTRY_DSN = RAW_SENTRY_DSN || undefined;

// Logging configuration
export const ENABLE_LOGGING = process.env.NEXT_PUBLIC_ENABLE_LOGGING === 'true';
export const LOG_LEVEL = process.env.NEXT_PUBLIC_LOG_LEVEL ?? 'warn';

// Assets and keys
export const R2_URL = process.env.NEXT_PUBLIC_R2_URL ?? 'https://assets.instainstru.com';
export const IMAGE_OPTIMIZATION = process.env.NEXT_PUBLIC_IMAGE_OPTIMIZATION === 'true';
export const JAWG_TOKEN = process.env.NEXT_PUBLIC_JAWG_TOKEN;
export const STRIPE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
export const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;

// Feature flags
export const IS_STAFF_PREVIEW = process.env.NEXT_PUBLIC_IS_STAFF_PREVIEW === 'true';

// Node environment (for server-side code)
export const NODE_ENV = process.env.NODE_ENV ?? 'development';
export const IS_PRODUCTION = NODE_ENV === 'production';
export const IS_DEVELOPMENT = NODE_ENV === 'development';
export const IS_TEST = NODE_ENV === 'test';
export const IS_CI = process.env.CI === 'true';

export const publicEnv = {
  NEXT_PUBLIC_API_BASE: RAW_API_BASE,
  NEXT_PUBLIC_APP_ENV: RAW_APP_ENV ?? '',
  NEXT_PUBLIC_ENV: RAW_PUBLIC_ENV ?? '',
  NEXT_PUBLIC_SENTRY_DSN: RAW_SENTRY_DSN,
  NEXT_PUBLIC_USE_PROXY: RAW_USE_PROXY,
  NEXT_PUBLIC_APP_URL: RAW_APP_URL,
  NEXT_PUBLIC_TURNSTILE_SITE_KEY: TURNSTILE_SITE_KEY ?? '',
} as const;
