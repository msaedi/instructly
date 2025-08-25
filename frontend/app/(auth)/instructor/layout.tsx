'use client';

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';

export default function InstructorAuthLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isLoading, user } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      const ret = encodeURIComponent(pathname || '/');
      router.replace(`/login?redirect=${ret}`);
      return;
    }
    const roles = Array.isArray(user?.roles) ? user!.roles : [];
    const isAdmin = roles.includes('admin');
    const isInstructor = roles.includes('instructor');
    if (isAdmin) {
      router.replace('/admin/analytics/codebase');
      return;
    }
    if (!isInstructor) {
      // Authenticated but not an instructor: route to student area
      router.replace('/student/dashboard');
    }
  }, [isAuthenticated, isLoading, user, router, pathname]);

  if (isLoading) return null;
  // While redirecting, avoid flashing
  const roles = Array.isArray(user?.roles) ? user!.roles : [];
  const isAdmin = roles.includes('admin');
  const isInstructor = roles.includes('instructor');
  if (!isAuthenticated || isAdmin || !isInstructor) return null;

  return <>{children}</>;
}
