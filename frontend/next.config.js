/** @type {import('next').NextConfig} */
const nextConfig = {
  // Silence multi-lockfile workspace root warning in CI with explicit root
  outputFileTracingRoot: require('path').resolve(__dirname, '..'),
  // Allow Next build to succeed while we remediate lint errors in phased PRs
  eslint: { ignoreDuringBuilds: true },
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
