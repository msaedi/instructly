import type { NextConfig } from 'next';

const CACHE_HEADER = { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' };

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: {
    formats: ['image/avif', 'image/webp'],
  },
  // Allow dev asset loading from local beta host for testing
  allowedDevOrigins: ['beta-local.instainstru.com'],
  // No legacy redirects; all links should point to Phoenix paths directly
  headers: async () => {
    return [
      {
        source: '/_next/static/:path*',
        headers: [CACHE_HEADER],
      },
      {
        source: '/_next/image',
        headers: [CACHE_HEADER],
      },
      {
        source: '/fonts/:path*',
        headers: [CACHE_HEADER],
      },
      {
        source: '/images/:path*',
        headers: [CACHE_HEADER],
      },
      {
        source: '/:path*',
        headers: [
          // Enable HSTS in production behind HTTPS; browsers will ignore if HTTP
          { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains; preload' },
        ],
      },
    ];
  },
};

export default nextConfig;
