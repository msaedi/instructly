// frontend/app/(auth)/layout.tsx
'use client';

/**
 * Auth layout - wraps all authenticated routes (student + instructor).
 *
 * Provides UserMessageStreamProvider for real-time messaging across
 * all authenticated areas.
 *
 * Phase 4: Single SSE connection for all user conversations.
 */

import { UserMessageStreamProvider } from '@/providers/UserMessageStreamProvider';

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <UserMessageStreamProvider>{children}</UserMessageStreamProvider>;
}
