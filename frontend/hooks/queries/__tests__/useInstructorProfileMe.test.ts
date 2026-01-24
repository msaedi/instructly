/**
 * @jest-environment jsdom
 */
import { renderHook } from '@testing-library/react';
import type { InstructorProfile } from '@/types/instructor';

const mockUseGetMyProfile = jest.fn();

jest.mock('@/src/api/generated/instructors-v1/instructors-v1', () => ({
  useGetMyProfileApiV1InstructorsMeGet: (...args: unknown[]) => mockUseGetMyProfile(...args),
}));

jest.mock('@/src/api/queryKeys', () => ({
  queryKeys: {
    instructors: {
      me: ['instructors', 'me'],
    },
  },
}));

import { useInstructorProfileMe } from '../useInstructorProfileMe';

describe('useInstructorProfileMe', () => {
  beforeEach(() => {
    mockUseGetMyProfile.mockReset();
    mockUseGetMyProfile.mockReturnValue({ data: { id: 'inst-1' } });
  });

  it('uses default enabled value', () => {
    const { result } = renderHook(() => useInstructorProfileMe());

    expect(mockUseGetMyProfile).toHaveBeenCalledWith({
      query: expect.objectContaining({
        queryKey: ['instructors', 'me'],
        enabled: true,
      }),
    });
    expect(result.current.data).toEqual({ id: 'inst-1' } as InstructorProfile);
  });

  it('passes through disabled flag', () => {
    renderHook(() => useInstructorProfileMe(false));

    expect(mockUseGetMyProfile).toHaveBeenCalledWith({
      query: expect.objectContaining({
        enabled: false,
      }),
    });
  });
});
