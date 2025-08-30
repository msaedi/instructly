'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useBetaAccess } from '@/features/shared/hooks/useBetaAccess';

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isLoading, user } = useAuth();
  const { sitePhase } = useBetaAccess();

  useEffect(() => {
    if (isLoading) return;

    // Server-side phase: block student routes during instructor_only
    if (sitePhase === 'instructor_only') {
      router.replace('/');
      return;
    }

    if (!isAuthenticated) {
      const ret = encodeURIComponent(pathname || '/');
      router.replace(`/login?redirect=${ret}`);
      return;
    }
    const roles = Array.isArray(user?.roles) ? user!.roles : [];
    const isAdmin = roles.includes('admin');
    const isInstructor = roles.includes('instructor');
    const isStudent = roles.includes('student') || (!isInstructor && !isAdmin);
    if (isAdmin) {
      router.replace('/admin/analytics/codebase');
      return;
    }
    if (!isStudent) {
      // Authenticated instructor should not be in student-only layout
      router.replace('/instructor/dashboard');
    }
  }, [isAuthenticated, isLoading, user, router, pathname, sitePhase]);

  return (
    <>
      {children}
    </>
  );
}
