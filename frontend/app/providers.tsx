// frontend/app/providers.tsx
'use client';

import { ReactNode, useEffect } from 'react';
import { AuthProvider } from '@/features/shared/hooks/useAuth';
import { useGuestSessionCleanup } from '@/hooks/useGuestSessionCleanup';
import { initializeSessionTracking, cleanupSessionTracking } from '@/lib/sessionTracking';

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
    <AuthProvider>
      <AppInitializer>{children}</AppInitializer>
    </AuthProvider>
  );
}
