// frontend/app/providers.tsx
'use client';

import { ReactNode } from 'react';
import { AuthProvider } from '@/features/shared/hooks/useAuth';

export function Providers({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
