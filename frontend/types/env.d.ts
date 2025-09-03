declare namespace NodeJS {
  interface ProcessEnv {
    // Required
    NEXT_PUBLIC_API_BASE: string;

    // Optional
    NEXT_PUBLIC_APP_ENV?: 'local' | 'preview' | 'beta' | 'ci' | 'e2e' | 'production';
    NEXT_PUBLIC_USE_PROXY?: 'true' | 'false';
    NEXT_PUBLIC_APP_URL?: string;
    NEXT_PUBLIC_ENABLE_LOGGING?: string;
    NEXT_PUBLIC_LOG_LEVEL?: string;
    NEXT_PUBLIC_R2_URL?: string;
    NEXT_PUBLIC_IMAGE_OPTIMIZATION?: string;
    NEXT_PUBLIC_JAWG_TOKEN?: string;
    NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY?: string;
    NEXT_PUBLIC_IS_STAFF_PREVIEW?: string;

    // Node environment
    NODE_ENV?: 'development' | 'production' | 'test';
    CI?: string;

    // Test-specific
    E2E_USER_EMAIL?: string;
    E2E_USER_PASSWORD?: string;
  }
}
