// frontend/app/config/brand.ts

/**
 * Centralized Brand Configuration for InstaInstru
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

export const BRAND = {
  // Core brand identity
  name: "iNSTAiNSTRU",
  tagline: "Book Expert Instructors Instantly",
  description: "Connect with expert instructors in NYC for personalized lessons in yoga, music, languages, fitness, and more.",
  
  // Domain and URLs
  domain: "instainstru.com",
  url: {
    production: "https://instainstru.com",
    staging: "https://instructly-ten.vercel.app",
    api: {
      production: "https://api.instainstru.com",
      staging: "https://instructly.onrender.com"
    }
  },
  
  // Contact information
  email: {
    support: "support@instainstru.com",
    noreply: "noreply@auth.instainstru.com",
    hello: "hello@instainstru.com"
  },
  
  // Social media (for future use)
  social: {
    twitter: "@instainstru",
    instagram: "@instainstru",
    facebook: "instainstru"
  },
  
  // Legal
  legal: {
    companyName: "InstaInstru LLC",
    foundedYear: 2024
  },
  
  // SEO
  seo: {
    defaultTitle: "InstaInstru - Book Expert Instructors Instantly",
    titleTemplate: "%s | InstaInstru",
    defaultDescription: "Find and book expert instructors in NYC for yoga, music, languages, fitness, and more. Instant booking, verified instructors.",
    keywords: ["instructors", "lessons", "NYC", "yoga", "music", "fitness", "tutoring", "coaching"],
  },
  
  // Brand colors (for future use in email templates, PDFs, etc.)
  colors: {
    primary: "#4f46e5", // Indigo 600
    primaryDark: "#4338ca", // Indigo 700
    secondary: "#06b6d4", // Cyan 500
    success: "#10b981", // Emerald 500
    warning: "#f59e0b", // Amber 500
    error: "#ef4444", // Red 500
  },
  
  // Feature flags (for gradual rollout)
  features: {
    messaging: false,
    payments: false,
    reviews: false,
    mobileApp: false,
  }
} as const;

/**
 * Type-safe brand configuration
 * 
 * Use this type when passing brand config around:
 * ```tsx
 * function EmailTemplate(brand: BrandConfig) { ... }
 * ```
 */
export type BrandConfig = typeof BRAND;

/**
 * Helper function to get the appropriate API URL based on environment
 * 
 * @returns The API URL for the current environment
 * 
 * @example
 * ```tsx
 * const apiUrl = getApiUrl();
 * // In production: "https://api.instainstru.com"
 * // In development: "https://instructly.onrender.com"
 * ```
 */
export function getApiUrl(): string {
  return process.env.NODE_ENV === 'production' 
    ? BRAND.url.api.production 
    : BRAND.url.api.staging;
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
  return process.env.NODE_ENV === 'production' 
    ? BRAND.url.production 
    : BRAND.url.staging;
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
 * // Returns: "InstaInstru Support <support@instainstru.com>"
 * ```
 */
export function getEmailWithName(type: keyof typeof BRAND.email): string {
  const email = BRAND.email[type];
  const nameMap = {
    support: 'InstaInstru Support',
    noreply: 'InstaInstru',
    hello: 'InstaInstru Team'
  };
  
  return `${nameMap[type]} <${email}>`;
}