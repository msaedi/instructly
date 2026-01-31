import * as Sentry from '@sentry/nextjs';

import { logger } from './lib/logger';
import { PUBLIC_ENV, SENTRY_DSN } from './lib/publicEnv';

const isProd = process.env.NODE_ENV === 'production';
const environment = PUBLIC_ENV || process.env['VERCEL_ENV'] || 'development';
const enabled = isProd && Boolean(SENTRY_DSN);
const shouldDebug = PUBLIC_ENV !== 'production';

Sentry.init({
  dsn: SENTRY_DSN,
  tunnel: '/monitoring',
  enabled,
  environment,
  release: process.env['VERCEL_GIT_COMMIT_SHA'],
  sendDefaultPii: true,
  tracesSampleRate: 0,
  replaysOnErrorSampleRate: 1.0,
  replaysSessionSampleRate: 0.1,
  integrations: [
    Sentry.replayIntegration({
      maskAllText: false,
      blockAllMedia: false,
    }),
  ],
  enableLogs: true,
});

if (shouldDebug && typeof window !== 'undefined') {
  // Useful in beta/preview to verify client init and DSN wiring.
  // DSN is public, safe to include in logs.
  logger.info('[Sentry] client config', { dsn: SENTRY_DSN, enabled, environment, isProd });
}
