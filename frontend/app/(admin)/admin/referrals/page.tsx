import type { Metadata } from 'next';
import ReferralsAdminClient from './ReferralsAdminClient';

export const metadata: Metadata = {
  title: 'Referrals Admin',
};

export default function ReferralsAdminPage() {
  return <ReferralsAdminClient />;
}
