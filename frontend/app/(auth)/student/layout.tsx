'use client';

import { usePathname } from 'next/navigation';
import { StudentHeader } from '@/components/layout/StudentHeader';

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Don't show StudentHeader on booking confirmation page
  const hideHeader = pathname === '/student/booking/confirm';

  return (
    <>
      {!hideHeader && <StudentHeader />}
      {children}
    </>
  );
}
