import type { Metadata } from 'next';
import { Suspense } from 'react';

import PaymentsAdminClient from './PaymentsAdminClient';

export const metadata: Metadata = {
  title: 'Payments Admin',
};

export default function PaymentsAdminPage() {
  return (
    <Suspense
      fallback={(
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
        </div>
      )}
    >
      <PaymentsAdminClient />
    </Suspense>
  );
}
