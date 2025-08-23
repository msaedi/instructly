import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  // No legacy redirects; all links should point to Phoenix paths directly
};

export default nextConfig;
