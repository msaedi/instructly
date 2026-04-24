import type { components } from '@/features/shared/api/types';

export type AccountStatus = components['schemas']['AccountStatusResponse']['account_status'];

/**
 * Check if an account is in a paused state.
 * Note: backend status is 'suspended' but the UX-facing term is 'paused'.
 */
export function isPaused(status: AccountStatus | null | undefined): boolean {
  return status === 'suspended';
}
