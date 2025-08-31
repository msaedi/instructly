/** @type {import('next').NextConfig} */
const nextConfig = {
  // Re-enable normal lint behavior during build
  eslint: {},
  async headers() {
    // Apply noindex/nofollow + private cache on preview/beta (can be toggled via env if needed)
    if (process.env.NEXT_PUBLIC_APP_ENV === 'preview' || process.env.NEXT_PUBLIC_APP_ENV === 'beta') {
      return [
        {
          source: '/:path*',
          headers: [
            { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
            { key: 'Cache-Control', value: 'private, no-store' },
          ],
        },
      ]
    }
    return []
  },
}

module.exports = nextConfig
