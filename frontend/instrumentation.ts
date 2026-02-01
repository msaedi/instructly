import * as Sentry from '@sentry/nextjs';
import { registerOTel } from '@vercel/otel';

import { logger } from '@/lib/logger';

const OTEL_DISABLED_MESSAGE = 'OpenTelemetry disabled (ENABLE_OTEL !== "true")';
const OTEL_ENABLED_MESSAGE = 'OpenTelemetry initialized for Next.js';

const OTEL_PROPAGATION_URLS = [
  /^https?:\/\/api\.instainstru\.com/,
  /^https?:\/\/.*\.onrender\.com/,
  /^https?:\/\/localhost:8000/,
];

function registerServerOtel(): void {
  const enableOtel = process.env['ENABLE_OTEL'] === 'true';

  if (!enableOtel) {
    logger.info(OTEL_DISABLED_MESSAGE);
    return;
  }

  registerOTel({
    serviceName: process.env['OTEL_SERVICE_NAME'] || 'instainstru-web',
    instrumentationConfig: {
      fetch: {
        propagateContextUrls: OTEL_PROPAGATION_URLS,
      },
    },
  });

  logger.info(OTEL_ENABLED_MESSAGE);
}

export async function register() {
  registerServerOtel();

  if (process.env['NEXT_RUNTIME'] === 'nodejs') {
    await import('./sentry.server.config');
  }
  if (process.env['NEXT_RUNTIME'] === 'edge') {
    await import('./sentry.edge.config');
  }
}

export const onRequestError = Sentry.captureRequestError;
