/**
 * Tests for useAuth debug/non-production code paths.
 *
 * Line 121: logger.debug('[TRACE] checkAuth()') -- only fires when IS_PRODUCTION is false.
 * Lines 211, 224: router.replace('/') -- only fires when typeof window === 'undefined'.
 *
 * These paths are unreachable in the main test file because:
 *   - IS_PRODUCTION is mocked as true
 *   - jsdom always defines window
 */

import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('@/lib/publicEnv', () => ({
  IS_PRODUCTION: false,
}));

jest.mock('@/lib/http', () => {
  const actual = jest.requireActual('@/lib/http');
  return {
    ...actual,
    http: jest.fn(),
    httpGet: jest.fn(),
  };
});

jest.mock('@/lib/searchTracking', () => ({
  getGuestSessionId: jest.fn().mockReturnValue(null),
  transferGuestSearchesToAccount: jest.fn(),
  clearGuestSession: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  },
}));

import { useRouter } from 'next/navigation';
import { AuthProvider, useAuth } from '../useAuth';
import { httpGet } from '@/lib/http';
import { logger } from '@/lib/logger';

const useRouterMock = useRouter as jest.Mock;
const httpGetMock = httpGet as jest.Mock;
const loggerDebugMock = logger.debug as jest.Mock;

const mockUser = {
  id: 'user-1',
  email: 'test@example.com',
  first_name: 'Test',
  last_name: 'User',
  permissions: [],
};

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
  Wrapper.displayName = 'AuthDebugWrapper';
  return Wrapper;
};

describe('useAuth -- non-production checkAuth debug logging (line 121)', () => {
  const push = jest.fn();
  const replace = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({ push, replace });
    httpGetMock.mockResolvedValue(mockUser);
  });

  it('logs TRACE checkAuth() when IS_PRODUCTION is false', async () => {
    httpGetMock.mockResolvedValueOnce(mockUser);

    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    httpGetMock.mockResolvedValueOnce({ ...mockUser, first_name: 'Updated' });

    await act(async () => {
      await result.current.checkAuth();
    });

    // checkAuth should have logged TRACE because IS_PRODUCTION is false
    expect(loggerDebugMock).toHaveBeenCalledWith(
      '[TRACE] checkAuth()',
      expect.objectContaining({ count: expect.any(Number) })
    );
  });
});
