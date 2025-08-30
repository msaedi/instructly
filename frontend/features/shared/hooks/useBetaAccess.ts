'use client';

import { useMemo } from 'react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useBeta } from '@/contexts/BetaContext';

export interface BetaAccessInfo {
  sitePhase: string; // from hostname (e.g., instructor_only, alpha, open)
  hasUserBetaAccess: boolean;
  userBetaRole?: string;
  userBetaPhase?: string;
  invitedByCode?: string | null;
}

export function useBetaAccess(): BetaAccessInfo {
  const { user } = useAuth();
  const { config } = useBeta();

  const info = useMemo(() => {
    const hasUserBetaAccess = Boolean((user as any)?.beta_access);
    const userBetaRole = (user as any)?.beta_role as string | undefined;
    const userBetaPhase = (user as any)?.beta_phase as string | undefined;
    const invitedByCode = (user as any)?.beta_invited_by as string | undefined;
    return {
      sitePhase: config.phase,
      hasUserBetaAccess,
      userBetaRole,
      userBetaPhase,
      invitedByCode: invitedByCode ?? null,
    } as BetaAccessInfo;
  }, [user, config.phase]);

  return info;
}
