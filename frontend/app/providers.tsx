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
import { Toaster } from 'sonner';
// Reverted: Analytics now handled in layout or removed by user preference

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

  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AppInitializer>{children}</AppInitializer>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: '#5b21b6',
              color: '#fdf4ff',
              padding: '12px 16px',
              borderRadius: '12px',
              width: 'auto',
              minWidth: '260px',
              maxWidth: '360px',
              whiteSpace: 'normal',
              boxShadow: '0 12px 24px rgba(15, 23, 42, 0.45)',
            },
            classNames: {
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
