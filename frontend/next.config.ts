import type { NextConfig } from 'next';
import { withSentryConfig } from '@sentry/nextjs';
import { withAxiom } from 'next-axiom';
import { withBotId } from 'botid/next/config';

const cspReportUri = (() => {
  const dsn = process.env['NEXT_PUBLIC_SENTRY_DSN'] || '';
  if (!dsn) {
    return '/monitoring';
  }

  try {
    const parsed = new URL(dsn);
    const projectId = parsed.pathname.replace(/^\/+/, '').split('/')[0];
    const sentryKey = parsed.username;
    if (!projectId || !sentryKey) {
      return '/monitoring';
    }
    return `${parsed.protocol}//${parsed.host}/api/${projectId}/security/?sentry_key=${sentryKey}`;
  } catch {
    return '/monitoring';
  }
})();

const cspApiOrigin = (() => {
  const apiBase = process.env['NEXT_PUBLIC_API_BASE'] || process.env['NEXT_PUBLIC_API_URL'] || '';
  if (!apiBase) {
    const appEnv = (process.env['NEXT_PUBLIC_APP_ENV'] || '').toLowerCase();
    const isDevLike =
      process.env.NODE_ENV !== 'production' ||
      appEnv === 'local' ||
      appEnv === 'development' ||
      appEnv === 'dev';
    return isDevLike ? 'http://localhost:8000' : '';
  }

  try {
    return new URL(apiBase).origin;
  } catch {
    return '';
  }
})();

const cspBetaLocalOrigin = (() => {
  const appEnv = (process.env['NEXT_PUBLIC_APP_ENV'] || '').toLowerCase();
  const isDevLike =
    process.env.NODE_ENV !== 'production' ||
    appEnv === 'local' ||
    appEnv === 'development' ||
    appEnv === 'dev';
  return isDevLike ? 'http://api.beta-local.instainstru.com:8000' : '';
})();

const connectSrcOrigins = [
  "'self'",
  cspApiOrigin,
  cspBetaLocalOrigin,
  'https://preview-api.instainstru.com',
  'https://api.instainstru.com',
  'https://*.sentry.io',
  'https://*.stripe.com',
  'https://challenges.cloudflare.com',
  'https://*.leadsy.ai',
  'https://vitals.vercel-insights.com',
  'https://*.axiom.co',
  'https://*.onrender.com',
  // 100ms video uses region-specific signaling/init hosts that may change by account/region.
  // Keeping wildcard for now to avoid production breakage.
  // Docs: https://www.100ms.live/docs
  // TODO: tighten to explicit subdomains once 100ms publishes a stable endpoint list.
  // Override via NEXT_PUBLIC_100MS_CONNECT_ORIGINS if needed.
  ...(
    process.env['NEXT_PUBLIC_100MS_CONNECT_ORIGINS'] ||
    'https://*.100ms.live,wss://*.100ms.live,https://storage.googleapis.com'
  )
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean),
];

const cspPolicyValue = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com https://verify.stripe.com https://challenges.cloudflare.com https://*.leadsy.ai https://tag.trovo-tag.com https://va.vercel-scripts.com",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com",
  "img-src 'self' data: blob: https://assets.instainstru.com https://*.cloudflare.com https://*.stripe.com https://*.tile.jawg.io https://*.basemaps.cartocdn.com https://*.100ms.live",
  `connect-src ${Array.from(new Set(connectSrcOrigins.filter(Boolean))).join(' ')}`,
  "frame-src 'self' https://js.stripe.com https://hooks.stripe.com https://verify.stripe.com https://challenges.cloudflare.com https://tag.trovo-tag.com",
  "font-src 'self' data: https://fonts.gstatic.com",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "media-src 'self' blob: https://*.100ms.live https://100ms.live",
  "worker-src 'self' blob:",
  `report-uri ${cspReportUri}`,
].join('; ');

const nextConfig: NextConfig = {
  // Stub @mediapipe/selfie_segmentation — Closure Compiler CJS output that Turbopack
  // cannot resolve as ESM. Virtual background is unused; stub prevents build failure
  // while keeping @100mslive/roomkit-react functional.
  turbopack: {
    resolveAlias: {
      '@mediapipe/selfie_segmentation': './stubs/mediapipe-selfie-segmentation.js',
    },
  },
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
      { key: 'Permissions-Policy', value: 'camera=(self), microphone=(self), geolocation=()' },
      { key: 'Content-Security-Policy', value: cspPolicyValue },
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

export default withBotId(withAxiom(withSentryConfig(nextConfig, sentryBuildOptions)));
