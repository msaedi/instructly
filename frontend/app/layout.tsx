// frontend/app/layout.tsx
import { BRAND } from '@/app/config/brand';
import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { logger } from '@/lib/logger';
import { Providers } from './providers';
import { Analytics } from '@vercel/analytics/next';
import { SpeedInsights } from '@vercel/speed-insights/next';
import GlobalBackground from '../components/ui/GlobalBackground';
import PreviewRibbon from '../components/PreviewRibbon';
import { BetaProvider, BetaBanner } from '@/contexts/BetaContext';
import { BackgroundProvider } from '@/lib/config/backgroundProvider';
import { env } from '@/lib/env';
// Analytics moved to client-only Providers to avoid SSR hydration mismatch

/**
 * Geist Sans Font Configuration
 *
 * Modern, clean sans-serif font for UI elements and body text
 */
const _geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

/**
 * Geist Mono Font Configuration
 *
 * Monospace font for code snippets, technical information, or fixed-width needs
 */
const _geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

/**
 * Metadata Configuration
 *
 * SEO and social media metadata for the entire application.
 * Individual pages can override these defaults.
 */
export const metadata: Metadata = {
  title: {
    template: `%s | ${BRAND.name}`,
    default: BRAND.seo.defaultTitle,
  },
  description:
    BRAND.seo.defaultDescription ||
    'Book trusted instructors for any skill - from yoga to music to languages. Learn from verified NYC experts.',
  keywords: [
    'instructors',
    'lessons',
    'NYC',
    'tutoring',
    'skills',
    'learning',
    'yoga',
    'music',
    'languages',
  ],
  authors: [{ name: BRAND.name }],
  creator: BRAND.name,
  publisher: BRAND.name,
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
  metadataBase: new URL(env.get('NEXT_PUBLIC_APP_URL') || 'https://instainstru.com'),
  openGraph: {
    title: BRAND.seo.defaultTitle,
    description:
      BRAND.seo.defaultDescription ||
      'Book trusted instructors for any skill - from yoga to music to languages.',
    url: '/',
    siteName: BRAND.name,
    locale: 'en_US',
    type: 'website',
    images: [
      {
        url: '/og-image.png', // TODO: Add actual OG image
        width: 1200,
        height: 630,
        alt: `${BRAND.name} - Book trusted instructors`,
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: BRAND.seo.defaultTitle,
    description: BRAND.seo.defaultDescription || 'Book trusted instructors for any skill',
    creator: BRAND.social?.twitter,
    images: ['/twitter-image.png'], // TODO: Add actual Twitter image
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  icons: {
    icon: '/favicon.ico',
    // Use only existing icons to avoid 404s
  },
};

/**
 * RootLayout Component
 *
 * The root layout wrapper for the entire Next.js application.
 * Applies global fonts, styles, and provides the HTML structure.
 *
 * Features:
 * - Custom font loading (Geist Sans and Mono)
 * - Global CSS application
 * - Antialiased text rendering
 * - Semantic HTML structure
 * - Dark mode support via CSS custom properties
 * - Structured logging for layout initialization
 *
 * @param {Object} props - Component props
 * @param {React.ReactNode} props.children - Child components to render
 * @returns {React.ReactElement} The root HTML structure
 */
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Log layout initialization in development
  logger.debug('Root layout initialized', {
    brand: BRAND.name,
    environment: env.get('NODE_ENV'),
    appUrl: env.get('NEXT_PUBLIC_APP_URL'),
    loggingEnabled: env.get('NEXT_PUBLIC_ENABLE_LOGGING') === 'true',
  });

  return (
    <html lang="en" className="h-full">
      <head>
        {/* Leaflet CSS */}
        <link
          rel="stylesheet"
          href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
          integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
          crossOrigin=""
        />
      </head>
      <body
        className={`h-full antialiased bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 ${_geistSans.variable} ${_geistMono.variable}`}
        style={{ isolation: 'isolate' }}
      >
        <BackgroundProvider>
          {/* Global fixed background with blur-up and readability overlay */}
          <GlobalBackground />
          <BetaProvider>
            {env.get('NEXT_PUBLIC_APP_ENV') === 'preview' ? <PreviewRibbon /> : null}
            <BetaBanner />
            {/* Future enhancements could include:
              - Global error boundary
              - Analytics provider
              - Toast notifications provider
              - Theme provider
            */}
            <Providers>
              {children}
              <Analytics />
              <SpeedInsights />
            </Providers>
          </BetaProvider>
        </BackgroundProvider>
      </body>
    </html>
  );
}
