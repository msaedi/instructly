import type { Metadata } from 'next';
import PaymentsAdminClient from './PaymentsAdminClient';

// eslint-disable-next-line react-refresh/only-export-components
export const metadata: Metadata = {
  title: 'Payments Admin',
};

export default function PaymentsAdminPage() {
  return <PaymentsAdminClient />;
}
