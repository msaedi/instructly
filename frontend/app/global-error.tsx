'use client';

import * as Sentry from '@sentry/nextjs';
import { useEffect } from 'react';
import { formatSupportCode, getSupportCode } from '@/lib/errors/supportCode';

export default function GlobalError({
  error,
}: {
  error: Error & { digest?: string };
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  const supportCode = getSupportCode(error);

  return (
    <html lang="en">
      <body>
        <h1>Something went wrong.</h1>
        <p>Please refresh the page or try again later.</p>
        {supportCode && (
          <p>
            If you need help, reference code: <code>{formatSupportCode(supportCode)}</code>
          </p>
        )}
      </body>
    </html>
  );
}
