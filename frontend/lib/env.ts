/**
 * Centralized environment variable access to avoid TypeScript index signature errors
 * This module provides typed getters for process.env that comply with strict TypeScript rules.
 *
 * IMPORTANT:
 * - Do NOT use this module for NEXT_PUBLIC_* in client-side code. Next.js requires literal
 *   access (process.env.NEXT_PUBLIC_*) for build-time inlining. Use `@/lib/publicEnv` instead.
 * - This helper is intended for server-only envs or non-public values.
 */

export const env = {
  /**
   * Get an optional environment variable
   * @param key The environment variable name
   * @returns The value or undefined
   */
  get: (key: string): string | undefined => {
    return process.env[key];
  },

  /**
   * Get a required environment variable (throws if not set)
   * @param key The environment variable name
   * @returns The value (never undefined)
   *
   * @throws Error if the environment variable is not set
   */
  require: (key: string): string => {
    const value = process.env[key];
    if (!value) {
      throw new Error(`Environment variable ${key} is required but not set`);
    }
    return value;
  },

  /**
   * Get an environment variable with a default fallback
   * @param key The environment variable name
   * @param defaultValue The fallback value if not set
   * @returns The value or the default
   */
  getOrDefault: (key: string, defaultValue: string): string => {
    return process.env[key] ?? defaultValue;
  },

  /**
   * Check if an environment variable is set
   * @param key The environment variable name
   * @returns true if the variable is set (even if empty string)
   */
  has: (key: string): boolean => {
    return key in process.env;
  },

  /**
   * Check if running in development mode
   */
  isDevelopment: (): boolean => {
    return process.env['NODE_ENV'] === 'development';
  },

  /**
   * Check if running in production mode
   */
  isProduction: (): boolean => {
    return process.env['NODE_ENV'] === 'production';
  },

  /**
   * Check if running in test mode
   */
  isTest: (): boolean => {
    return process.env['NODE_ENV'] === 'test';
  },

  /**
   * Check if running in CI
   */
  isCI: (): boolean => {
    return process.env['CI'] === 'true';
  },
};

// Common environment variables as constants for easy access
export const NODE_ENV = env.get('NODE_ENV') ?? 'development';
export const NEXT_PUBLIC_API_BASE = env.get('NEXT_PUBLIC_API_BASE');
export const NEXT_PUBLIC_APP_URL = env.get('NEXT_PUBLIC_APP_URL');
export const NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY = env.get('NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY');
export const NEXT_PUBLIC_GOOGLE_MAPS_API_KEY = env.get('NEXT_PUBLIC_GOOGLE_MAPS_API_KEY');
export const NEXT_TELEMETRY_DISABLED = env.get('NEXT_TELEMETRY_DISABLED');
