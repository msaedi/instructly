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

    // Check if we have a token even if user data is still loading
    const hasToken = typeof window !== 'undefined' && !!localStorage.getItem('access_token');

    if (!isAuthenticated && !hasToken) {
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

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  return (
    <>
      {children}
    </>
  );
}
