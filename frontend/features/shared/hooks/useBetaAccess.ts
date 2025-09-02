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
    const hasUserBetaAccess = Boolean(user && 'beta_access' in user && user.beta_access);
    const userBetaRole = user && 'beta_role' in user && typeof user.beta_role === 'string' ? user.beta_role : undefined;
    const userBetaPhase = user && 'beta_phase' in user && typeof user.beta_phase === 'string' ? user.beta_phase : undefined;
    const invitedByCode = user && 'beta_invited_by' in user && typeof user.beta_invited_by === 'string' ? user.beta_invited_by : undefined;
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
