'use client';

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';

import { InstructorReferralPopup } from '@/components/instructor/InstructorReferralPopup';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { useAuth } from '@/features/shared/hooks/useAuth';

export default function InstructorAuthLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isLoading, user } = useAuth();
  const roles = Array.isArray(user?.roles) ? user?.roles ?? [] : [];
  const isInstructor = roles.includes('instructor');
  const isOnboardingPage = pathname?.startsWith('/instructor/onboarding') ?? false;
  const { data: instructorProfile } = useInstructorProfileMe(isInstructor && !isOnboardingPage);
  const isLive = instructorProfile?.is_live === true;

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
      router.replace('/admin/engineering/codebase');
      return;
    }
    if (!isInstructor) {
      // Authenticated but not an instructor: route to student area
      router.replace('/student/dashboard');
    }
  }, [isAuthenticated, isLoading, user, router, pathname]);

  if (isLoading) return null;
  // While redirecting, avoid flashing
  const isAdmin = roles.includes('admin');
  if (!isAuthenticated || isAdmin || !isInstructor) return null;

  return (
    <>
      {children}
      <InstructorReferralPopup isLive={isLive} />
    </>
  );
}
