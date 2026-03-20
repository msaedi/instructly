/**
 * @jest-environment jsdom
 */
import { renderHook } from '@testing-library/react';

import { useInstructorCommissionStatus } from '@/src/api/services/instructors';

jest.mock('@/src/api/services/instructors', () => ({
  useInstructorCommissionStatus: jest.fn(),
}));

import { useCommissionStatus } from '../useCommissionStatus';

describe('useCommissionStatus', () => {
  const mockUseInstructorCommissionStatus = useInstructorCommissionStatus as jest.MockedFunction<
    typeof useInstructorCommissionStatus
  >;

  beforeEach(() => {
    mockUseInstructorCommissionStatus.mockReset();
    mockUseInstructorCommissionStatus.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useInstructorCommissionStatus>);
  });

  it('re-exports the instructor commission status hook', () => {
    expect(useCommissionStatus).toBe(useInstructorCommissionStatus);
  });

  it('passes options through to the instructor commission status hook', () => {
    mockUseInstructorCommissionStatus.mockReturnValue({
      data: {
        is_founding: false,
        tier_name: 'entry',
        commission_rate_pct: 15,
        activity_window_days: 30,
        completed_lessons_30d: 3,
        next_tier_name: 'growth',
        next_tier_threshold: 5,
        lessons_to_next_tier: 2,
        tiers: [],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useInstructorCommissionStatus>);

    const { result } = renderHook(() => useCommissionStatus({ enabled: false }));

    expect(mockUseInstructorCommissionStatus).toHaveBeenCalledWith({ enabled: false });
    expect(result.current).toEqual(
      expect.objectContaining({
        data: expect.objectContaining({
          tier_name: 'entry',
          commission_rate_pct: 15,
        }),
      })
    );
  });

  it('forwards undefined options unchanged', () => {
    renderHook(() => useCommissionStatus());

    expect(mockUseInstructorCommissionStatus).toHaveBeenCalledWith();
  });
});
