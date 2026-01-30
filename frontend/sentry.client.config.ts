import * as Sentry from '@sentry/nextjs';

import { PUBLIC_ENV, SENTRY_DSN } from './lib/publicEnv';

const isProd = process.env.NODE_ENV === 'production';
const environment = PUBLIC_ENV || process.env['VERCEL_ENV'] || 'development';

Sentry.init({
  dsn: SENTRY_DSN,
  tunnel: '/monitoring',
  enabled: isProd && Boolean(SENTRY_DSN),
  environment,
  release: process.env['VERCEL_GIT_COMMIT_SHA'],
  sendDefaultPii: true,
  tracesSampleRate: 0.1,
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
