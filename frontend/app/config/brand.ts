// frontend/app/config/brand.ts

import { IS_PRODUCTION } from '@/lib/publicEnv';

/**
 * Centralized Brand Configuration for iNSTAiNSTRU
 *
 * This file contains all brand-related constants to ensure consistency
 * across the application. Update here to change branding everywhere.
 *
 * @module brand
 *
 * Usage:
 * ```tsx
 * import { BRAND } from '@/app/config/brand';
 *
 * // In components
 * <h1>{BRAND.name}</h1>
 * <meta name="description" content={BRAND.seo.defaultDescription} />
 * ```
 */

/**
 * URL configuration type
 */
export interface BrandUrls {
  production: string;
  staging: string;
  api: {
    production: string;
    staging: string;
  };
}

/**
 * Email configuration type
 */
export interface BrandEmails {
  support: string;
  noreply: string;
  hello: string;
}

/**
 * Social media configuration type
 */
export interface BrandSocial {
  twitter: string;
  instagram: string;
  facebook: string;
}

/**
 * Legal information type
 */
export interface BrandLegal {
  companyName: string;
  foundedYear: number;
}

/**
 * SEO configuration type
 */
export interface BrandSeo {
  defaultTitle: string;
  titleTemplate: string;
  defaultDescription: string;
  keywords: string[];
}

/**
 * Brand colors type
 */
export interface BrandColors {
  primary: string;
  primaryDark: string;
  secondary: string;
  success: string;
  warning: string;
  error: string;
}

/**
 * Feature flags type
 */
export interface BrandFeatures {
  messaging: boolean;
  payments: boolean;
  reviews: boolean;
  mobileApp: boolean;
}

/**
 * Complete brand configuration type
 */
export interface BrandConfig {
  name: string;
  tagline: string;
  description: string;
  domain: string;
  url: BrandUrls;
  email: BrandEmails;
  social: BrandSocial;
  legal: BrandLegal;
  seo: BrandSeo;
  colors: BrandColors;
  features: BrandFeatures;
}

export const BRAND: BrandConfig = {
  // Core brand identity
  name: 'iNSTAiNSTRU',
  tagline: 'Book Expert Instructors Instantly',
  description:
    'Connect with expert instructors in NYC for personalized lessons in yoga, music, languages, fitness, and more.',

  // Domain and URLs
  domain: 'instainstru.com',
  url: {
    production: 'https://instainstru.com',
    staging: 'https://instructly-ten.vercel.app',
    api: {
      production: 'https://api.instainstru.com',
      staging: 'https://instructly-0949.onrender.com',
    },
  },

  // Contact information
  email: {
    support: 'support@instainstru.com',
    noreply: 'noreply@auth.instainstru.com',
    hello: 'hello@instainstru.com',
  },

  // Social media (for future use)
  social: {
    twitter: '@instainstru',
    instagram: '@instainstru',
    facebook: 'instainstru',
  },

  // Legal
  legal: {
    companyName: 'iNSTAiNSTRU LLC',
    foundedYear: 2024,
  },

  // SEO
  seo: {
    defaultTitle: 'iNSTAiNSTRU - Book Expert Instructors Instantly',
    titleTemplate: '%s | iNSTAiNSTRU',
    defaultDescription:
      'Find and book expert instructors in NYC for yoga, music, languages, fitness, and more. Instant booking, verified instructors.',
    keywords: ['instructors', 'lessons', 'NYC', 'yoga', 'music', 'fitness', 'tutoring', 'coaching'],
  },

  // Brand colors (for future use in email templates, PDFs, etc.)
  colors: {
    primary: '#4f46e5', // Indigo 600
    primaryDark: '#4338ca', // Indigo 700
    secondary: '#06b6d4', // Cyan 500
    success: '#10b981', // Emerald 500
    warning: '#f59e0b', // Amber 500
    error: '#ef4444', // Red 500
  },

  // Feature flags (for gradual rollout)
  features: {
    messaging: false,
    payments: false,
    reviews: false,
    mobileApp: false,
  },
} as const;

/**
 * Email type for getEmailWithName function
 */
export type EmailType = keyof BrandEmails;

/**
 * Helper function to get the appropriate API URL based on environment
 *
 * @returns The API URL for the current environment
 *
 * @example
 * ```tsx
 * const apiUrl = getApiUrl();
 * // In production: "https://api.instainstru.com"
 * // In development: "https://instructly-0949.onrender.com'"
 * ```
 */
export function getApiUrl(): string {
  return IS_PRODUCTION ? BRAND.url.api.production : BRAND.url.api.staging;
}

/**
 * Helper function to get the appropriate app URL based on environment
 *
 * @returns The app URL for the current environment
 *
 * @example
 * ```tsx
 * const appUrl = getAppUrl();
 * // In production: "https://instainstru.com"
 * // In development: "https://instructly-ten.vercel.app"
 * ```
 */
export function getAppUrl(): string {
  return IS_PRODUCTION ? BRAND.url.production : BRAND.url.staging;
}

/**
 * Helper function to format email addresses with brand name
 *
 * @param type - The type of email (support, noreply, hello)
 * @returns Formatted email string with brand name
 *
 * @example
 * ```tsx
 * const supportEmail = getEmailWithName('support');
 * // Returns: "iNSTAiNSTRU Support <support@instainstru.com>"
 * ```
 */
export function getEmailWithName(type: EmailType): string {
  const email = BRAND.email[type];
  const nameMap: Record<EmailType, string> = {
    support: 'iNSTAiNSTRU Support',
    noreply: 'iNSTAiNSTRU',
    hello: 'iNSTAiNSTRU Team',
  };

  return `${nameMap[type]} <${email}>`;
}
