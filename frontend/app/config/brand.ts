// frontend/app/config/brand.ts

/**
 * Centralized brand configuration for InstaInstru
 * 
 * This file contains all brand-related constants to ensure consistency
 * across the application. Update here to change branding everywhere.
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
    }
  } as const;
  
  // Type-safe brand configuration
  export type BrandConfig = typeof BRAND;