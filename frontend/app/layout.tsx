// frontend/app/layout.tsx
import { BRAND } from '@/app/config/brand';
import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { logger } from '@/lib/logger';
import { Providers } from './providers';

/**
 * Geist Sans Font Configuration
 *
 * Modern, clean sans-serif font for UI elements and body text
 */
const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

/**
 * Geist Mono Font Configuration
 *
 * Monospace font for code snippets, technical information, or fixed-width needs
 */
const geistMono = Geist_Mono({
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
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || 'https://instainstru.com'),
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
    shortcut: '/favicon-16x16.png',
    apple: '/apple-touch-icon.png',
  },
  manifest: '/site.webmanifest',
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
    environment: process.env.NODE_ENV,
    appUrl: process.env.NEXT_PUBLIC_APP_URL,
    loggingEnabled: process.env.NEXT_PUBLIC_ENABLE_LOGGING === 'true',
  });

  return (
    <html lang="en" className="h-full">
      <head>{/* Additional meta tags can be added here if needed */}</head>
      <body
        className="h-full antialiased bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
        style={{ isolation: 'isolate' }}
      >
        {/* Future enhancements could include:
            - Global error boundary
            - Analytics provider
            - Toast notifications provider
            - Theme provider
        */}
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
