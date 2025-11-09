import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
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
      // Enable HSTS in production behind HTTPS; browsers will ignore if HTTP
      { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains; preload' },
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

export default nextConfig;
