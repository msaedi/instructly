import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PLATFORM_CONFIG_QUERY_KEY, usePlatformConfig, usePlatformFees } from '../usePlatformConfig';

jest.mock('@/lib/api/config', () => ({
  fetchPlatformConfig: jest.fn(),
}));

const { fetchPlatformConfig } = require('@/lib/api/config') as {
  fetchPlatformConfig: jest.Mock;
};

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return Wrapper;
};

describe('usePlatformConfig', () => {
  beforeEach(() => {
    fetchPlatformConfig.mockReset();
  });

  it('exports a stable public platform config query key', () => {
    expect(PLATFORM_CONFIG_QUERY_KEY).toEqual(['config', 'public']);
  });

  it('returns config data when fetch succeeds (line 15)', async () => {
    const mockConfig = {
      fees: {
        founding_instructor: 0.08,
        tier_1: 0.15,
        tier_2: 0.12,
        tier_3: 0.10,
        student_booking_fee: 0.12,
      },
      student_launch_enabled: false,
    };
    fetchPlatformConfig.mockResolvedValue(mockConfig);

    const { result } = renderHook(() => usePlatformConfig(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.config).toEqual(mockConfig);
    expect(result.current.error).toBeNull();
  });

  it('returns null config and error message on failure', async () => {
    fetchPlatformConfig.mockRejectedValue(new Error('Network failure'));

    const { result } = renderHook(() => usePlatformConfig(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.config).toBeNull();
    expect(result.current.error).toBe('Unable to load platform configuration.');
  });
});

describe('usePlatformFees', () => {
  beforeEach(() => {
    fetchPlatformConfig.mockReset();
  });

  it('returns fallback fees when config is not available', async () => {
    fetchPlatformConfig.mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => usePlatformFees(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.fees.student_booking_fee).toBe(0.12);
    expect(result.current.fees.founding_instructor).toBe(0.08);
  });

  it('returns config fees when available', async () => {
    const customFees = {
      founding_instructor: 0.05,
      tier_1: 0.10,
      tier_2: 0.08,
      tier_3: 0.06,
      student_booking_fee: 0.10,
    };
    fetchPlatformConfig.mockResolvedValue({ fees: customFees, student_launch_enabled: true });

    const { result } = renderHook(() => usePlatformFees(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.fees).toEqual(customFees);
  });

  it('preserves the student launch flag on the raw platform config', async () => {
    fetchPlatformConfig.mockResolvedValue({
      fees: {
        founding_instructor: 0.08,
        tier_1: 0.15,
        tier_2: 0.12,
        tier_3: 0.10,
        student_booking_fee: 0.12,
      },
      student_launch_enabled: true,
    });

    const { result } = renderHook(() => usePlatformConfig(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.config?.student_launch_enabled).toBe(true);
  });
});
