'use client';

import * as Sentry from '@sentry/nextjs';

export default function SentryExamplePage() {
  const triggerError = () => {
    Sentry.captureException(new Error('Sentry Frontend Test Error'));
  };

  return (
    <div style={{ padding: '2rem' }}>
      <h1>Sentry Example Page</h1>
      <p>Click the button below to send a test event to Sentry.</p>
      <button
        type="button"
        onClick={triggerError}
        className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
      >
        Trigger Sentry Error
      </button>
    </div>
  );
}
