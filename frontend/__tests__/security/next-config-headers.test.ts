jest.mock('@sentry/nextjs', () => ({
  withSentryConfig: (config: unknown) => config,
}));

jest.mock('next-axiom', () => ({
  withAxiom: (config: unknown) => config,
}));

jest.mock('botid/next/config', () => ({
  withBotId: (config: unknown) => config,
}));

describe('next.config security headers', () => {
  const mutableEnv = process.env as Record<string, string | undefined>;
  const originalDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  const originalNodeEnv = process.env.NODE_ENV;
  const originalAppEnv = process.env.NEXT_PUBLIC_APP_ENV;
  const originalVercelEnv = process.env.VERCEL_ENV;
  const original100msOrigins = process.env.NEXT_PUBLIC_100MS_CONNECT_ORIGINS;

  afterEach(() => {
    if (originalDsn === undefined) {
      delete mutableEnv.NEXT_PUBLIC_SENTRY_DSN;
    } else {
      mutableEnv.NEXT_PUBLIC_SENTRY_DSN = originalDsn;
    }
    if (originalNodeEnv === undefined) {
      delete mutableEnv.NODE_ENV;
    } else {
      mutableEnv.NODE_ENV = originalNodeEnv;
    }
    if (originalAppEnv === undefined) {
      delete mutableEnv.NEXT_PUBLIC_APP_ENV;
    } else {
      mutableEnv.NEXT_PUBLIC_APP_ENV = originalAppEnv;
    }
    if (originalVercelEnv === undefined) {
      delete mutableEnv.VERCEL_ENV;
    } else {
      mutableEnv.VERCEL_ENV = originalVercelEnv;
    }
    if (original100msOrigins === undefined) {
      delete mutableEnv.NEXT_PUBLIC_100MS_CONNECT_ORIGINS;
    } else {
      mutableEnv.NEXT_PUBLIC_100MS_CONNECT_ORIGINS = original100msOrigins;
    }
    jest.resetModules();
  });

  it('includes enforcing CSP header with required directives', async () => {
    mutableEnv.NEXT_PUBLIC_SENTRY_DSN = '';
    jest.resetModules();

    const configModule = await import('../../next.config');
    const nextConfig = configModule.default as {
      headers?: () => Promise<Array<{ source: string; headers: Array<{ key: string; value: string }> }>>;
    };

    expect(nextConfig.headers).toBeDefined();
    const headerRules = await nextConfig.headers!();
    const rootRule = headerRules.find((rule) => rule.source === '/:path*');
    expect(rootRule).toBeDefined();

    const cspHeader = rootRule!.headers.find(
      (header) => header.key === 'Content-Security-Policy'
    );
    expect(cspHeader).toBeDefined();

    const cspValue = cspHeader!.value;
    expect(cspValue).toContain("default-src 'self'");
    expect(cspValue).toContain('https://js.stripe.com');
    expect(cspValue).toContain('https://challenges.cloudflare.com');
    expect(cspValue).toContain('https://*.leadsy.ai');
    expect(cspValue).toContain('https://preview-api.instainstru.com');
    expect(cspValue).toContain('https://api.instainstru.com');
    expect(cspValue).toContain('http://localhost:8000');
    expect(cspValue).toContain('https://*.100ms.live');
    expect(cspValue).toContain('wss://*.100ms.live');
    expect(cspValue).toContain('report-uri /monitoring');
  });

  it('requires explicit 100ms origins in strict production runtime', async () => {
    mutableEnv.NODE_ENV = 'production';
    mutableEnv.NEXT_PUBLIC_APP_ENV = 'production';
    delete mutableEnv.VERCEL_ENV;
    mutableEnv.NEXT_PUBLIC_SENTRY_DSN = '';
    delete mutableEnv.NEXT_PUBLIC_100MS_CONNECT_ORIGINS;
    jest.resetModules();

    await expect(import('../../next.config')).rejects.toThrow(
      'NEXT_PUBLIC_100MS_CONNECT_ORIGINS must be set in production'
    );
  });

  it('uses explicit 100ms origins in production without wildcard defaults', async () => {
    mutableEnv.NODE_ENV = 'production';
    mutableEnv.NEXT_PUBLIC_APP_ENV = 'production';
    delete mutableEnv.VERCEL_ENV;
    mutableEnv.NEXT_PUBLIC_SENTRY_DSN = '';
    mutableEnv.NEXT_PUBLIC_100MS_CONNECT_ORIGINS =
      'https://rtm.prod.100ms.live,wss://rtm.prod.100ms.live,https://storage.googleapis.com';
    jest.resetModules();

    const configModule = await import('../../next.config');
    const nextConfig = configModule.default as {
      headers?: () => Promise<Array<{ source: string; headers: Array<{ key: string; value: string }> }>>;
    };

    const headerRules = await nextConfig.headers!();
    const rootRule = headerRules.find((rule) => rule.source === '/:path*');
    const cspHeader = rootRule!.headers.find(
      (header) => header.key === 'Content-Security-Policy'
    );
    const cspValue = cspHeader!.value;

    expect(cspValue).toContain('https://rtm.prod.100ms.live');
    expect(cspValue).toContain('wss://rtm.prod.100ms.live');
    expect(cspValue).toContain('https://storage.googleapis.com');
    expect(cspValue).not.toContain('https://*.100ms.live');
    expect(cspValue).not.toContain('wss://*.100ms.live');
  });
});
