// frontend/app/providers.tsx
'use client';

import { ReactNode } from 'react';
import { AuthProvider } from '@/features/shared/hooks/useAuth';
import { useGuestSessionCleanup } from '@/hooks/useGuestSessionCleanup';

function AppInitializer({ children }: { children: ReactNode }) {
  // Initialize guest session cleanup on app mount
  useGuestSessionCleanup();

  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AppInitializer>{children}</AppInitializer>
    </AuthProvider>
  );
}
