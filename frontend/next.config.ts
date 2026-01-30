import type { NextConfig } from 'next';
import { withSentryConfig } from '@sentry/nextjs';

const nextConfig: NextConfig = {
  distDir: process.env['NEXT_DIST_DIR'] || '.next',
  env: {
    NEXT_PUBLIC_LH_CI: process.env['NEXT_PUBLIC_LH_CI'] || '',
  },
  rewrites: async () => ({
    beforeFiles: [],
    afterFiles: [],
    fallback: [],
  }),
  // outputFileTracingRoot must stay scoped to this app directory to avoid Vercel's /path0/path0 issue.
  outputFileTracingRoot: process.cwd(),
  // Allow dev asset loading from local beta host for testing
  allowedDevOrigins: ['beta-local.instainstru.com'],
  images: {
    formats: ['image/avif', 'image/webp'],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'assets.instainstru.com',
        pathname: '/**',
      },
    ],
  },
  // No legacy redirects; all links should point to Phoenix paths directly
  headers: async () => {
    const isPreviewEnv =
      process.env.NEXT_PUBLIC_APP_ENV === 'preview' || process.env.NEXT_PUBLIC_APP_ENV === 'beta';

    const rootHeaders = [
      { key: 'X-DNS-Prefetch-Control', value: 'on' },
      { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'origin-when-cross-origin' },
      { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
      // Enable HSTS behind HTTPS; browsers will ignore if HTTP
      { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
    ];

    if (isPreviewEnv) {
      rootHeaders.push(
        { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
        { key: 'Cache-Control', value: 'private, no-store' }
      );
    }

    const immutableCacheHeaders = ['/_next/static/:path*', '/_next/image/:path*', '/fonts/:path*', '/images/:path*'].map(
      (source) => ({
        source,
        headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
      })
    );

    return [
      {
        source: '/:path*',
        headers: rootHeaders,
      },
      ...immutableCacheHeaders,
    ];
  },
};

const isProd = process.env.NODE_ENV === 'production';
const sentryAuthToken = process.env['SENTRY_AUTH_TOKEN'];
const sentryOrg = process.env['SENTRY_ORG'];
const sentryProject = process.env['SENTRY_PROJECT'];
const releaseName = process.env['VERCEL_GIT_COMMIT_SHA'];
const shouldUploadSourceMaps = Boolean(isProd && sentryAuthToken && sentryOrg && sentryProject);

const sentryBuildOptions = {
  ...(sentryAuthToken ? { authToken: sentryAuthToken } : {}),
  ...(sentryOrg ? { org: sentryOrg } : {}),
  ...(sentryProject ? { project: sentryProject } : {}),
  ...(releaseName ? { release: { name: releaseName } } : {}),
  tunnelRoute: '/monitoring',
  silent: true,
  sourcemaps: {
    disable: !shouldUploadSourceMaps,
  },
  widenClientFileUpload: true,
  webpack: {
    treeshake: {
      removeDebugLogging: true,
    },
  },
};

export default withSentryConfig(nextConfig, sentryBuildOptions);
