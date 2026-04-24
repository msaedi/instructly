// frontend/app/providers.tsx
'use client';

import { ReactNode, useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { AuthProvider } from '@/features/shared/hooks/useAuth';
import { useGuestSessionCleanup } from '@/hooks/useGuestSessionCleanup';
import { ensureGuestOnce } from '@/lib/searchTracking';
import { initializeSessionTracking, cleanupSessionTracking } from '@/lib/sessionTracking';
import { queryClient } from '@/lib/react-query/queryClient';
import { AlertTriangle, Check, Info, LoaderCircle, X } from 'lucide-react';
import { Toaster, toast } from 'sonner';
import {
  ACCOUNT_DELETED_TOAST_KEY,
  ACCOUNT_DELETED_TOAST_MESSAGE,
} from '@/lib/accountDeletedToast';
// Reverted: Analytics now handled in layout or removed by user preference

function ToastIcon({ children }: { children: ReactNode }) {
  return (
    <span className="inst-toast-icon-circle" aria-hidden="true">
      {children}
    </span>
  );
}

function AppInitializer({ children }: { children: ReactNode }) {
  // Initialize guest session cleanup on app mount
  useGuestSessionCleanup();

  // Initialize session tracking for analytics
  useEffect(() => {
    initializeSessionTracking();

    // Bootstrap guest session once for anonymous users
    ensureGuestOnce().catch(() => {});

    // Cleanup on unmount
    return () => {
      cleanupSessionTracking();
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || window.location.pathname !== '/') {
      return;
    }

    try {
      const hasDeletedToast = window.sessionStorage.getItem(ACCOUNT_DELETED_TOAST_KEY);
      if (!hasDeletedToast) {
        return;
      }
      window.sessionStorage.removeItem(ACCOUNT_DELETED_TOAST_KEY);
      toast.success(ACCOUNT_DELETED_TOAST_MESSAGE);
    } catch {
      // Ignore storage access errors.
    }
  }, []);

  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AppInitializer>{children}</AppInitializer>
        <Toaster
          expand={true}
          position="top-right"
          icons={{
            success: <ToastIcon><Check /></ToastIcon>,
            error: <ToastIcon><X /></ToastIcon>,
            warning: <ToastIcon><AlertTriangle /></ToastIcon>,
            info: <ToastIcon><Info /></ToastIcon>,
            loading: <ToastIcon><LoaderCircle className="animate-spin" /></ToastIcon>,
          }}
          toastOptions={{
            style: {
              padding: '12px 16px',
              borderRadius: '12px',
              width: 'auto',
              minWidth: '260px',
              maxWidth: '360px',
              whiteSpace: 'normal',
              boxShadow: '0 12px 24px rgba(15, 23, 42, 0.45)',
            },
            classNames: {
              default: 'inst-toast-brand',
              success: 'inst-toast-brand',
              info: 'inst-toast-brand',
              loading: 'inst-toast-brand',
              error: 'inst-toast-brand',
              warning: 'inst-toast-brand',
              icon: 'inst-toast-icon',
              title: 'inst-toast-title',
              description: 'inst-toast-description',
            },
          }}
        />
      </AuthProvider>
      {/* React Query DevTools - Only visible in development */}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
