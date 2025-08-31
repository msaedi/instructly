import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  // Default to noindex on preview/beta; GA app can override per environment variable
  return { rules: [{ userAgent: '*', disallow: '/' }] }
}
