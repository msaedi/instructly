import type { Metadata } from 'next';
import ReferralsAdminClient from './ReferralsAdminClient';

// eslint-disable-next-line react-refresh/only-export-components
export const metadata: Metadata = {
  title: 'Referrals Admin',
};

export default function ReferralsAdminPage() {
  return <ReferralsAdminClient />;
}
