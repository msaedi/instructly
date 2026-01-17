import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useInstructorReferralStats,
  useReferredInstructors,
  useFoundingStatus,
  useReferralPopupData,
  formatCents,
  getPayoutStatusDisplay,
} from '../useInstructorReferrals';
import { instructorReferralsApi } from '@/services/api/instructorReferrals';

jest.mock('@/services/api/instructorReferrals', () => ({
  instructorReferralsApi: {
    getStats: jest.fn(),
    getReferredInstructors: jest.fn(),
    getFoundingStatus: jest.fn(),
    getPopupData: jest.fn(),
  },
}));

const getStatsMock = instructorReferralsApi.getStats as jest.Mock;
const getReferredMock = instructorReferralsApi.getReferredInstructors as jest.Mock;
const getFoundingMock = instructorReferralsApi.getFoundingStatus as jest.Mock;
const getPopupMock = instructorReferralsApi.getPopupData as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper };
};

describe('useInstructorReferralStats', () => {
  beforeEach(() => {
    getStatsMock.mockReset();
  });

  it('returns referral stats on success', async () => {
    getStatsMock.mockResolvedValueOnce({ referralCode: 'CODE' });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInstructorReferralStats(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.referralCode).toBe('CODE');
  });

  it('reports errors when the API fails', async () => {
    getStatsMock.mockRejectedValueOnce(new Error('Failed'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInstructorReferralStats(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed');
  });

  it('does not run when disabled', async () => {
    const { wrapper } = createWrapper();
    renderHook(() => useInstructorReferralStats(false), { wrapper });

    await waitFor(() => expect(getStatsMock).not.toHaveBeenCalled());
  });
});

describe('useReferredInstructors', () => {
  beforeEach(() => {
    getReferredMock.mockReset();
  });

  it('returns referred instructors on success', async () => {
    getReferredMock.mockResolvedValueOnce({ instructors: [{ id: '1' }], totalCount: 1 });

    const { wrapper } = createWrapper();
    const { result } = renderHook(
      () => useReferredInstructors({ limit: 5, offset: 0 }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getReferredMock).toHaveBeenCalledWith({ limit: 5, offset: 0 });
    expect(result.current.data?.instructors).toHaveLength(1);
  });

  it('reports errors when the API fails', async () => {
    getReferredMock.mockRejectedValueOnce(new Error('Failed'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReferredInstructors(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed');
  });

  it('does not run when disabled', async () => {
    const { wrapper } = createWrapper();
    renderHook(() => useReferredInstructors(undefined, false), { wrapper });

    await waitFor(() => expect(getReferredMock).not.toHaveBeenCalled());
  });
});

describe('useFoundingStatus', () => {
  beforeEach(() => {
    getFoundingMock.mockReset();
  });

  it('returns founding status on success', async () => {
    getFoundingMock.mockResolvedValueOnce({ isFoundingPhase: true });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFoundingStatus(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.isFoundingPhase).toBe(true);
  });

  it('reports errors when the API fails', async () => {
    getFoundingMock.mockRejectedValueOnce(new Error('Failed'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFoundingStatus(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed');
  });

  it('does not run when disabled', async () => {
    const { wrapper } = createWrapper();
    renderHook(() => useFoundingStatus(false), { wrapper });

    await waitFor(() => expect(getFoundingMock).not.toHaveBeenCalled());
  });
});

describe('useReferralPopupData', () => {
  beforeEach(() => {
    getPopupMock.mockReset();
  });

  it('returns popup data on success', async () => {
    getPopupMock.mockResolvedValueOnce({ referralCode: 'POPUP' });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReferralPopupData(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.referralCode).toBe('POPUP');
  });

  it('reports errors when the API fails', async () => {
    getPopupMock.mockRejectedValueOnce(new Error('Failed'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useReferralPopupData(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed');
  });

  it('does not run when disabled', async () => {
    const { wrapper } = createWrapper();
    renderHook(() => useReferralPopupData(false), { wrapper });

    await waitFor(() => expect(getPopupMock).not.toHaveBeenCalled());
  });
});

describe('formatCents', () => {
  it('formats cents as dollars without decimals', () => {
    expect(formatCents(2500)).toBe('$25');
  });

  it('handles zero cents', () => {
    expect(formatCents(0)).toBe('$0');
  });

  it('rounds to the nearest dollar', () => {
    expect(formatCents(995)).toBe('$10');
  });
});

describe('getPayoutStatusDisplay', () => {
  it('maps pending_live to awaiting go-live', () => {
    expect(getPayoutStatusDisplay('pending_live')).toEqual({ label: 'Awaiting Go-Live', color: 'gray' });
  });

  it('maps paid to green status', () => {
    expect(getPayoutStatusDisplay('paid')).toEqual({ label: 'Paid', color: 'green' });
  });

  it('falls back to unknown for unexpected values', () => {
    expect(getPayoutStatusDisplay('unknown' as never)).toEqual({ label: 'Unknown', color: 'gray' });
  });
});
