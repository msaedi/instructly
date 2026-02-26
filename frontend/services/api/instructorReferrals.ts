import { httpGet } from '@/lib/http';
import { logger } from '@/lib/logger';
import type {
  ReferralStatsResponse,
  ReferredInstructorInfo,
  ReferredInstructorsResponse,
  FoundingStatusResponse,
  PopupDataResponse,
} from '@/features/shared/api/types';

const BASE_PATH = '/api/v1/instructor-referrals';

// Alias — generated uses ReferredInstructorInfo
type ReferredInstructorResponse = ReferredInstructorInfo;

export interface ReferralStats {
  referralCode: string;
  referralLink: string;
  totalReferred: number;
  pendingPayouts: number;
  completedPayouts: number;
  totalEarnedCents: number;
  isFoundingPhase: boolean;
  foundingSpotsRemaining: number;
  currentBonusCents: number;
}

export interface ReferredInstructor {
  id: string;
  firstName: string;
  lastInitial: string;
  referredAt: Date;
  isLive: boolean;
  wentLiveAt: Date | null;
  firstLessonCompletedAt: Date | null;
  payoutStatus: 'pending_live' | 'pending_lesson' | 'pending_transfer' | 'paid' | 'failed';
  payoutAmountCents: number | null;
}

export interface FoundingStatus {
  isFoundingPhase: boolean;
  totalFoundingSpots: number;
  spotsFilled: number;
  spotsRemaining: number;
}

export interface PopupData {
  isFoundingPhase: boolean;
  bonusAmountCents: number;
  foundingSpotsRemaining: number;
  referralCode: string;
  referralLink: string;
}

const parseDate = (value: string | null | undefined): Date | null => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? null : parsed;
};

const transformStats = (data: ReferralStatsResponse): ReferralStats => ({
  referralCode: data.referral_code,
  referralLink: data.referral_link,
  totalReferred: data.total_referred,
  pendingPayouts: data.pending_payouts,
  completedPayouts: data.completed_payouts,
  totalEarnedCents: data.total_earned_cents,
  isFoundingPhase: data.is_founding_phase,
  foundingSpotsRemaining: data.founding_spots_remaining,
  currentBonusCents: data.current_bonus_cents,
});

const transformReferredInstructor = (data: ReferredInstructorResponse): ReferredInstructor => ({
  id: data.id,
  firstName: data.first_name,
  lastInitial: data.last_initial,
  referredAt: new Date(data.referred_at),
  isLive: data.is_live,
  wentLiveAt: parseDate(data.went_live_at),
  firstLessonCompletedAt: parseDate(data.first_lesson_completed_at),
  payoutStatus: data.payout_status as ReferredInstructor['payoutStatus'],
  payoutAmountCents: data.payout_amount_cents ?? null,
});

const transformFoundingStatus = (data: FoundingStatusResponse): FoundingStatus => ({
  isFoundingPhase: data.is_founding_phase,
  totalFoundingSpots: data.total_founding_spots,
  spotsFilled: data.spots_filled,
  spotsRemaining: data.spots_remaining,
});

const transformPopupData = (data: PopupDataResponse): PopupData => ({
  isFoundingPhase: data.is_founding_phase,
  bonusAmountCents: data.bonus_amount_cents,
  foundingSpotsRemaining: data.founding_spots_remaining,
  referralCode: data.referral_code,
  referralLink: data.referral_link,
});

export const instructorReferralsApi = {
  getStats: async (): Promise<ReferralStats> => {
    try {
      const data = await httpGet<ReferralStatsResponse>(`${BASE_PATH}/stats`);
      return transformStats(data);
    } catch (error) {
      logger.error('Failed to load instructor referral stats', error);
      throw error;
    }
  },

  getReferredInstructors: async (params?: { limit?: number; offset?: number }): Promise<{
    instructors: ReferredInstructor[];
    totalCount: number;
  }> => {
    try {
      const data = await httpGet<ReferredInstructorsResponse>(
        `${BASE_PATH}/referred`,
        params ? { query: params } : undefined
      );
      return {
        instructors: data.instructors.map(transformReferredInstructor),
        totalCount: data.total_count,
      };
    } catch (error) {
      logger.error('Failed to load referred instructors', error);
      throw error;
    }
  },

  getFoundingStatus: async (): Promise<FoundingStatus> => {
    try {
      const data = await httpGet<FoundingStatusResponse>(`${BASE_PATH}/founding-status`);
      return transformFoundingStatus(data);
    } catch (error) {
      logger.error('Failed to load referral founding status', error);
      throw error;
    }
  },

  getPopupData: async (): Promise<PopupData> => {
    try {
      const data = await httpGet<PopupDataResponse>(`${BASE_PATH}/popup-data`);
      return transformPopupData(data);
    } catch (error) {
      logger.error('Failed to load instructor referral popup data', error);
      throw error;
    }
  },
};
