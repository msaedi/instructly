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
  const originalDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

  afterEach(() => {
    if (originalDsn === undefined) {
      delete process.env.NEXT_PUBLIC_SENTRY_DSN;
    } else {
      process.env.NEXT_PUBLIC_SENTRY_DSN = originalDsn;
    }
    jest.resetModules();
  });

  it('includes CSP report-only header with required directives', async () => {
    process.env.NEXT_PUBLIC_SENTRY_DSN = '';
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
      (header) => header.key === 'Content-Security-Policy-Report-Only'
    );
    expect(cspHeader).toBeDefined();

    const cspValue = cspHeader!.value;
    expect(cspValue).toContain("default-src 'self'");
    expect(cspValue).toContain('https://js.stripe.com');
    expect(cspValue).toContain('https://challenges.cloudflare.com');
    expect(cspValue).toContain('https://r2.leadsy.ai');
    expect(cspValue).toContain('https://preview-api.instainstru.com');
    expect(cspValue).toContain('https://api.instainstru.com');
    expect(cspValue).toContain('http://localhost:8000');
    expect(cspValue).toContain('report-uri /monitoring');
  });
});
