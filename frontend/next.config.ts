import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  // No legacy redirects; all links should point to Phoenix paths directly
  headers: async () => {
    return [
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
