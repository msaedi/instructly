import { fetchJson, ApiProblemError } from '@/lib/api/fetch';
import { logger } from '@/lib/logger';

export type PlatformFees = {
  founding_instructor: number;
  tier_1: number;
  tier_2: number;
  tier_3: number;
  student_booking_fee: number;
};

export type PlatformConfig = {
  fees: PlatformFees;
  updated_at?: string | null;
};

export async function fetchPlatformConfig(): Promise<PlatformConfig> {
  try {
    return await fetchJson<PlatformConfig>('/api/v1/config/public');
  } catch (error) {
    if (error instanceof ApiProblemError) {
      throw error;
    }
    logger.error('Failed to load platform config', error as Error);
    throw error;
  }
}
