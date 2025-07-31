// frontend/app/providers.tsx
'use client';

import { ReactNode, useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { AuthProvider } from '@/features/shared/hooks/useAuth';
import { useGuestSessionCleanup } from '@/hooks/useGuestSessionCleanup';
import { initializeSessionTracking, cleanupSessionTracking } from '@/lib/sessionTracking';
import { queryClient } from '@/lib/react-query/queryClient';

function AppInitializer({ children }: { children: ReactNode }) {
  // Initialize guest session cleanup on app mount
  useGuestSessionCleanup();

  // Initialize session tracking for analytics
  useEffect(() => {
    initializeSessionTracking();

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
      </AuthProvider>
      {/* React Query DevTools - Only visible in development */}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
