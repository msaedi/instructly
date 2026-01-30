'use client';

import * as Sentry from '@sentry/nextjs';

export default function SentryExamplePage() {
  const triggerError = () => {
    Sentry.captureException(new Error('Sentry Frontend Test Error'));
  };

  return (
    <main style={{ padding: '2rem' }}>
      <h1>Sentry Example Page</h1>
      <p>Click the button below to send a test event to Sentry.</p>
      <button type="button" onClick={triggerError}>
        Trigger Sentry Error
      </button>
    </main>
  );
}
