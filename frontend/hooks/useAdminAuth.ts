// frontend/hooks/useAdminAuth.ts
/**
 * Hook to check admin authentication and redirect if not authorized
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';

export function useAdminAuth() {
  const { user, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    // Don't redirect while loading
    if (isLoading) return;

    // Only redirect if we're definitely not authenticated (no token in localStorage)
    if (!isAuthenticated && !localStorage.getItem('access_token')) {
      router.push('/login?redirect=/admin/analytics/search');
      return;
    }

    // For now, only allow specific admin emails until admin role is implemented
    // In production, this should check for user.role === 'admin'
    const adminEmails = ['admin@instainstru.com', 'mehdi@instainstru.com'];

    if (user && !adminEmails.includes(user.email)) {
      // Redirect to home page for non-admins
      router.push('/');
    }
  }, [user, isAuthenticated, isLoading, router]);

  // Check if current user is admin
  const adminEmails = ['admin@instainstru.com', 'mehdi@instainstru.com'];
  const isAdmin = user ? adminEmails.includes(user.email) : false;

  return {
    isAdmin,
    isLoading,
    user,
  };
}
