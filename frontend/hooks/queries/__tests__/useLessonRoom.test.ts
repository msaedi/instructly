import React from 'react';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import { useJoinLesson, useVideoSessionStatus } from '../useLessonRoom';
import {
  useJoinLessonApiV1LessonsBookingIdJoinPost,
  useGetVideoSessionApiV1LessonsBookingIdVideoSessionGet,
} from '@/src/api/generated/lessons-v1/lessons-v1';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

jest.mock('@/src/api/generated/lessons-v1/lessons-v1', () => ({
  useJoinLessonApiV1LessonsBookingIdJoinPost: jest.fn(),
  useGetVideoSessionApiV1LessonsBookingIdVideoSessionGet: jest.fn(),
}));

const mockMutationHook = useJoinLessonApiV1LessonsBookingIdJoinPost as jest.Mock;
const mockQueryHook = useGetVideoSessionApiV1LessonsBookingIdVideoSessionGet as jest.Mock;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
};

// ---------------------------------------------------------------------------
// useJoinLesson
// ---------------------------------------------------------------------------

describe('useJoinLesson', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns joinLesson function, isPending and error', () => {
    const mutateAsync = jest.fn();
    mockMutationHook.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJoinLesson(), { wrapper });

    expect(typeof result.current.joinLesson).toBe('function');
    expect(result.current.isPending).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('reflects isPending from the underlying mutation', () => {
    mockMutationHook.mockReturnValue({
      mutateAsync: jest.fn(),
      isPending: true,
      error: null,
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJoinLesson(), { wrapper });

    expect(result.current.isPending).toBe(true);
  });

  it('calls mutateAsync with the correct bookingId', async () => {
    const mutateAsync = jest.fn().mockResolvedValue({ auth_token: 'tok', room_id: 'room_123' });
    mockMutationHook.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJoinLesson(), { wrapper });

    await act(async () => {
      await result.current.joinLesson('01BOOKING123456789012345');
    });

    expect(mutateAsync).toHaveBeenCalledWith({ bookingId: '01BOOKING123456789012345' });
  });

  it('returns the VideoJoinResponse from mutateAsync', async () => {
    const response = { auth_token: 'abc123', room_id: 'room_123', role: 'guest', booking_id: '01BOOKING123456789012345' };
    const mutateAsync = jest.fn().mockResolvedValue(response);
    mockMutationHook.mockReturnValue({
      mutateAsync,
      isPending: false,
      error: null,
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJoinLesson(), { wrapper });

    let returnValue: unknown;
    await act(async () => {
      returnValue = await result.current.joinLesson('01BOOKING123456789012345');
    });

    expect(returnValue).toEqual(response);
  });

  it('invalidates the booking detail cache on success', () => {
    let capturedOnSuccess: ((data: unknown, variables: { bookingId: string }) => void) | undefined;

    mockMutationHook.mockImplementation((opts: { mutation: { onSuccess: typeof capturedOnSuccess } }) => {
      capturedOnSuccess = opts.mutation.onSuccess;
      return { mutateAsync: jest.fn(), isPending: false, error: null };
    });

    const { wrapper, queryClient } = createWrapper();
    const spy = jest.spyOn(queryClient, 'invalidateQueries').mockResolvedValue(undefined);

    renderHook(() => useJoinLesson(), { wrapper });

    expect(capturedOnSuccess).toBeDefined();
    capturedOnSuccess!(undefined, { bookingId: '01BOOKING_ABC' });

    expect(spy).toHaveBeenCalledWith({
      queryKey: queryKeys.bookings.detail('01BOOKING_ABC'),
    });
  });

  it('exposes the mutation error', () => {
    const err = new Error('Network failure');
    mockMutationHook.mockReturnValue({
      mutateAsync: jest.fn(),
      isPending: false,
      error: err,
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useJoinLesson(), { wrapper });

    expect(result.current.error).toBe(err);
  });
});

// ---------------------------------------------------------------------------
// useVideoSessionStatus
// ---------------------------------------------------------------------------

describe('useVideoSessionStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns sessionData as null when query has no data', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useVideoSessionStatus('01BOOKING_XYZ'), {
      wrapper,
    });

    expect(result.current.sessionData).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(typeof result.current.refetch).toBe('function');
  });

  it('returns sessionData when query has data', () => {
    const sessionData = {
      room_id: 'room_123',
      session_started_at: '2025-01-01T10:00:00Z',
      session_ended_at: null,
      instructor_joined_at: null,
      student_joined_at: null,
    };

    mockQueryHook.mockReturnValue({
      data: sessionData,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useVideoSessionStatus('01BOOKING_XYZ'), {
      wrapper,
    });

    expect(result.current.sessionData).toEqual(sessionData);
  });

  it('returns isLoading true while query is loading', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useVideoSessionStatus('01BOOKING_XYZ'), {
      wrapper,
    });

    expect(result.current.isLoading).toBe(true);
  });

  it('exposes the query error', () => {
    const err = new Error('Session fetch failed');
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: err,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useVideoSessionStatus('01BOOKING_XYZ'), {
      wrapper,
    });

    expect(result.current.error).toBe(err);
  });

  it('passes bookingId to the generated query hook', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    renderHook(() => useVideoSessionStatus('01BOOKING_ABC'), { wrapper });

    expect(mockQueryHook).toHaveBeenCalledWith(
      '01BOOKING_ABC',
      expect.objectContaining({
        query: expect.objectContaining({
          queryKey: queryKeys.lessons.videoSession('01BOOKING_ABC'),
        }),
      }),
    );
  });

  it('passes pollingIntervalMs as refetchInterval', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    renderHook(
      () => useVideoSessionStatus('01BOOKING_ABC', { pollingIntervalMs: 3000 }),
      { wrapper },
    );

    const call = mockQueryHook.mock.calls[mockQueryHook.mock.calls.length - 1];
    expect(call?.[0]).toBe('01BOOKING_ABC');
    const refetchInterval = call?.[1]?.query?.refetchInterval;
    expect(typeof refetchInterval).toBe('function');
    expect(refetchInterval({ state: { data: null } })).toBe(3000);
  });

  it('stops polling when stopPollingWhenEnded is enabled and session has ended', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    renderHook(
      () => useVideoSessionStatus('01BOOKING_ABC', { pollingIntervalMs: 3000, stopPollingWhenEnded: true }),
      { wrapper },
    );

    const call = mockQueryHook.mock.calls[mockQueryHook.mock.calls.length - 1];
    const refetchInterval = call?.[1]?.query?.refetchInterval;
    expect(refetchInterval({ state: { data: { session_ended_at: '2025-01-01T10:00:00Z' } } })).toBe(false);
  });

  it('passes enabled option to the query', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    renderHook(
      () => useVideoSessionStatus('01BOOKING_ABC', { enabled: false }),
      { wrapper },
    );

    expect(mockQueryHook).toHaveBeenCalledWith(
      '01BOOKING_ABC',
      expect.objectContaining({
        query: expect.objectContaining({
          enabled: false,
        }),
      }),
    );
  });

  it('defaults enabled to true when not provided', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    renderHook(() => useVideoSessionStatus('01BOOKING_ABC'), { wrapper });

    expect(mockQueryHook).toHaveBeenCalledWith(
      '01BOOKING_ABC',
      expect.objectContaining({
        query: expect.objectContaining({
          enabled: true,
        }),
      }),
    );
  });

  it('omits refetchInterval when pollingIntervalMs is not provided', () => {
    mockQueryHook.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: jest.fn(),
    });

    const { wrapper } = createWrapper();
    renderHook(() => useVideoSessionStatus('01BOOKING_ABC'), { wrapper });

    const callArgs = mockQueryHook.mock.calls[0] as [string, { query: Record<string, unknown> }];
    expect(callArgs[1].query).not.toHaveProperty('refetchInterval');
  });
});
