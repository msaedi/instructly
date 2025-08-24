'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { StudentHeader } from '@/components/layout/StudentHeader';
import { useAuth } from '@/features/shared/hooks/useAuth';

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isLoading, user } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      const ret = encodeURIComponent(pathname || '/');
      router.replace(`/login?redirect=${ret}`);
      return;
    }
    const roles = Array.isArray(user?.roles) ? user!.roles : [];
    const isStudent = roles.includes('student') || !roles.includes('instructor');
    if (!isStudent) {
      // Authenticated instructor should not be in student-only layout
      router.replace('/instructor/dashboard');
    }
  }, [isAuthenticated, isLoading, user, router, pathname]);

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
