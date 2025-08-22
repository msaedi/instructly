'use client';

import { usePathname } from 'next/navigation';
import { StudentHeader } from '@/components/layout/StudentHeader';

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Don't show StudentHeader on booking confirmation page, lessons page, lesson details page, and review page
  const hideHeader = pathname === '/student/booking/confirm' ||
                     pathname === '/student/lessons' ||
                     pathname.startsWith('/student/lessons/') ||
                     pathname.startsWith('/student/review/');

  return (
    <>
      {!hideHeader && <StudentHeader />}
      {children}
    </>
  );
}
