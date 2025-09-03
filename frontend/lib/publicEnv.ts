/**
 * Public environment variables for Next.js
 *
 * IMPORTANT: This file uses literal process.env.NEXT_PUBLIC_* access
 * so that Next.js can inline these values at build time.
 *
 * DO NOT use dynamic access like process.env[key] or env.get(key) here!
 */

// Required environment variables
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE;

// Optional environment variables with defaults
export const APP_ENV = process.env.NEXT_PUBLIC_APP_ENV ?? 'local';
export const USE_PROXY = process.env.NEXT_PUBLIC_USE_PROXY === 'true';
export const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000';

// Logging configuration
export const ENABLE_LOGGING = process.env.NEXT_PUBLIC_ENABLE_LOGGING === 'true';
export const LOG_LEVEL = process.env.NEXT_PUBLIC_LOG_LEVEL ?? 'warn';

// Assets and keys
export const R2_URL = process.env.NEXT_PUBLIC_R2_URL ?? 'https://assets.instainstru.com';
export const IMAGE_OPTIMIZATION = process.env.NEXT_PUBLIC_IMAGE_OPTIMIZATION === 'true';
export const JAWG_TOKEN = process.env.NEXT_PUBLIC_JAWG_TOKEN;
export const STRIPE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;

// Feature flags
export const IS_STAFF_PREVIEW = process.env.NEXT_PUBLIC_IS_STAFF_PREVIEW === 'true';

// Node environment (for server-side code)
export const NODE_ENV = process.env.NODE_ENV ?? 'development';
export const IS_PRODUCTION = NODE_ENV === 'production';
export const IS_DEVELOPMENT = NODE_ENV === 'development';
export const IS_TEST = NODE_ENV === 'test';
export const IS_CI = process.env.CI === 'true';
