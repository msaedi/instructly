import type { ReactNode } from 'react';

export const dynamic = 'force-dynamic';

export default function AccountLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
