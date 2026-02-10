import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useUpcomingBookings,
  useRecentSearches,
  useFeaturedServices,
  useBookingHistory,
  useHomepageData,
} from '../useHomepage';
import { queryFn, convertApiResponse } from '@/lib/react-query/api';
import { publicApi } from '@/features/shared/api/client';
import { useCurrentUser } from '@/src/api/hooks/useSession';
import { httpJson } from '@/features/shared/api/http';
import { withApiBase } from '@/lib/apiBase';

jest.mock('@/lib/react-query/api', () => ({
  queryFn: jest.fn(),
  convertApiResponse: jest.fn(),
}));

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getRecentSearches: jest.fn(),
    getTopServicesPerCategory: jest.fn(),
  },
}));

jest.mock('@/src/api/hooks/useSession', () => ({
  useCurrentUser: jest.fn(),
}));

jest.mock('@/features/shared/api/http', () => ({
  httpJson: jest.fn(),
}));

jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((path: string) => `https://api.test${path}`),
}));

const queryFnMock = queryFn as jest.Mock;
const convertApiResponseMock = convertApiResponse as jest.Mock;
const getRecentSearchesMock = publicApi.getRecentSearches as jest.Mock;
const getTopServicesMock = publicApi.getTopServicesPerCategory as jest.Mock;
const useCurrentUserMock = useCurrentUser as jest.Mock;
const httpJsonMock = httpJson as jest.Mock;
const withApiBaseMock = withApiBase as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper };
};

describe('useUpcomingBookings', () => {
  beforeEach(() => {
    queryFnMock.mockReset();
    useCurrentUserMock.mockReset();
  });

  it('fetches upcoming bookings for authenticated users', async () => {
    const bookings = { items: [{ id: 'b1' }] };
    useCurrentUserMock.mockReturnValue({ id: 'user-1' });
    queryFnMock.mockReturnValue(() => Promise.resolve(bookings));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUpcomingBookings(2), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(bookings);
    expect(queryFnMock).toHaveBeenCalledWith('/api/v1/bookings/upcoming?limit=2', { requireAuth: true });
  });

  it('does not fetch when unauthenticated', async () => {
    useCurrentUserMock.mockReturnValue(null);
    queryFnMock.mockReturnValue(() => Promise.resolve({ items: [] }));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUpcomingBookings(3), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toBeUndefined();
  });

  it('surfaces errors from the query function', async () => {
    useCurrentUserMock.mockReturnValue({ id: 'user-2' });
    queryFnMock.mockReturnValue(() => Promise.reject(new Error('Boom')));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUpcomingBookings(1), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Boom');
  });
});

describe('useRecentSearches', () => {
  beforeEach(() => {
    getRecentSearchesMock.mockReset();
    convertApiResponseMock.mockReset();
  });

  it('returns recent searches on success', async () => {
    const apiResponse = { data: [{ id: 1 }], status: 200 };
    getRecentSearchesMock.mockResolvedValueOnce(apiResponse);
    convertApiResponseMock.mockReturnValue(apiResponse.data);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRecentSearches(3), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([{ id: 1 }]);
  });

  it('surfaces errors from convertApiResponse', async () => {
    getRecentSearchesMock.mockResolvedValueOnce({ data: null, status: 500, error: 'bad' });
    convertApiResponseMock.mockImplementation(() => {
      throw new Error('Parse failed');
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRecentSearches(2), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Parse failed');
  });

  it('passes the limit to the API', async () => {
    getRecentSearchesMock.mockResolvedValueOnce({ data: [], status: 200 });
    convertApiResponseMock.mockReturnValue([]);

    const { wrapper } = createWrapper();
    renderHook(() => useRecentSearches(5), { wrapper });

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalledWith(5));
  });
});

describe('useFeaturedServices', () => {
  beforeEach(() => {
    getTopServicesMock.mockReset();
    convertApiResponseMock.mockReset();
  });

  it('returns featured services on success', async () => {
    const apiResponse = { data: { categories: [] }, status: 200 };
    getTopServicesMock.mockResolvedValueOnce(apiResponse);
    convertApiResponseMock.mockReturnValue(apiResponse.data);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFeaturedServices(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ categories: [] });
  });

  it('surfaces errors from convertApiResponse', async () => {
    getTopServicesMock.mockResolvedValueOnce({ data: null, status: 500, error: 'bad' });
    convertApiResponseMock.mockImplementation(() => {
      throw new Error('Parse failed');
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useFeaturedServices(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Parse failed');
  });

  it('calls the top services API', async () => {
    getTopServicesMock.mockResolvedValueOnce({ data: [], status: 200 });
    convertApiResponseMock.mockReturnValue([]);

    const { wrapper } = createWrapper();
    renderHook(() => useFeaturedServices(), { wrapper });

    await waitFor(() => expect(getTopServicesMock).toHaveBeenCalled());
  });
});

describe('useBookingHistory', () => {
  beforeEach(() => {
    httpJsonMock.mockReset();
    useCurrentUserMock.mockReset();
    withApiBaseMock.mockClear();
  });

  it('fetches booking history for authenticated users', async () => {
    useCurrentUserMock.mockReturnValue({ id: 'user-3' });
    httpJsonMock.mockResolvedValueOnce({ items: [{ id: 'history-1' }] });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useBookingHistory(10), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
    expect(withApiBaseMock).toHaveBeenCalledWith('/api/v1/bookings?status=COMPLETED&per_page=10');
  });

  it('does not fetch when unauthenticated', async () => {
    useCurrentUserMock.mockReturnValue(null);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useBookingHistory(5), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toBeUndefined();
  });

  it('surfaces errors from httpJson', async () => {
    useCurrentUserMock.mockReturnValue({ id: 'user-4' });
    httpJsonMock.mockRejectedValueOnce(new Error('History failed'));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useBookingHistory(5), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('History failed');
  });
});

describe('useHomepageData', () => {
  beforeEach(() => {
    queryFnMock.mockReset();
    getRecentSearchesMock.mockReset();
    getTopServicesMock.mockReset();
    convertApiResponseMock.mockReset();
    useCurrentUserMock.mockReset();
    httpJsonMock.mockReset();
  });

  it('returns aggregated data when authenticated', async () => {
    useCurrentUserMock.mockReturnValue({ id: 'user-5' });
    queryFnMock.mockReturnValue(() => Promise.resolve({ items: [{ id: 'upcoming' }] }));
    getRecentSearchesMock.mockResolvedValueOnce({ data: [{ id: 'search' }], status: 200 });
    getTopServicesMock.mockResolvedValueOnce({ data: { categories: ['cat'] }, status: 200 });
    convertApiResponseMock.mockImplementation((response) => response.data);
    httpJsonMock.mockResolvedValueOnce({ items: [{ id: 'history' }] });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomepageData(), { wrapper });

    await waitFor(() => expect(result.current.isAnyLoading).toBe(false));
    expect(result.current.upcomingBookings.data?.items).toHaveLength(1);
    expect(result.current.recentSearches.data).toEqual([{ id: 'search' }]);
    expect(result.current.featuredServices.data).toEqual({ categories: ['cat'] });
    expect(result.current.bookingHistory.data?.items).toHaveLength(1);
  });

  it('omits authenticated-only data when unauthenticated', async () => {
    useCurrentUserMock.mockReturnValue(null);
    queryFnMock.mockReturnValue(() => Promise.resolve({ items: [] }));
    getRecentSearchesMock.mockResolvedValueOnce({ data: [], status: 200 });
    getTopServicesMock.mockResolvedValueOnce({ data: [], status: 200 });
    convertApiResponseMock.mockImplementation((response) => response.data);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomepageData(), { wrapper });

    await waitFor(() => expect(result.current.isAnyLoading).toBe(false));
    expect(result.current.upcomingBookings.data).toBeUndefined();
    expect(result.current.bookingHistory.data).toBeUndefined();
  });

  it('surfaces errors when a query fails', async () => {
    useCurrentUserMock.mockReturnValue({ id: 'user-6' });
    queryFnMock.mockReturnValue(() => Promise.resolve({ items: [] }));
    getRecentSearchesMock.mockResolvedValueOnce({ data: null, status: 500, error: 'bad' });
    convertApiResponseMock.mockImplementation(() => {
      throw new Error('Recent failed');
    });
    getTopServicesMock.mockResolvedValueOnce({ data: [], status: 200 });
    httpJsonMock.mockResolvedValueOnce({ items: [] });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomepageData(), { wrapper });

    await waitFor(() => expect(result.current.isAnyLoading).toBe(false));
    expect(result.current.recentSearches.error?.message).toBe('Recent failed');
  });

  it('omits data key from upcomingBookings when query data is undefined (unauthenticated)', async () => {
    useCurrentUserMock.mockReturnValue(null);
    queryFnMock.mockReturnValue(() => Promise.resolve(undefined));
    getRecentSearchesMock.mockResolvedValueOnce({ data: [], status: 200 });
    getTopServicesMock.mockResolvedValueOnce({ data: null, status: 200 });
    convertApiResponseMock.mockImplementation((response) => response.data ?? null);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomepageData(), { wrapper });

    await waitFor(() => expect(result.current.isAnyLoading).toBe(false));

    // When unauthenticated, upcomingBookings and bookingHistory should NOT have data key
    expect(result.current.upcomingBookings).not.toHaveProperty('data');
    expect(result.current.bookingHistory).not.toHaveProperty('data');
    // featuredServices also has undefined data, so no data key either
    expect(result.current.featuredServices).not.toHaveProperty('data');
  });

  it('includes data key in all sections when all queries return data', async () => {
    useCurrentUserMock.mockReturnValue({ id: 'user-7' });
    queryFnMock.mockReturnValue(() => Promise.resolve({ items: [{ id: 'up1' }] }));
    getRecentSearchesMock.mockResolvedValueOnce({ data: [{ id: 's1' }], status: 200 });
    getTopServicesMock.mockResolvedValueOnce({ data: { categories: ['music'] }, status: 200 });
    convertApiResponseMock.mockImplementation((response) => response.data);
    httpJsonMock.mockResolvedValueOnce({ items: [{ id: 'h1' }] });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomepageData(), { wrapper });

    await waitFor(() => expect(result.current.isAnyLoading).toBe(false));

    // All sections should have data key present
    expect(result.current.upcomingBookings).toHaveProperty('data');
    expect(result.current.upcomingBookings.data?.items).toHaveLength(1);
    expect(result.current.featuredServices).toHaveProperty('data');
    expect(result.current.featuredServices.data).toEqual({ categories: ['music'] });
    expect(result.current.bookingHistory).toHaveProperty('data');
    expect(result.current.bookingHistory.data?.items).toHaveLength(1);
  });

  it('reports isInitialLoading true when some queries are loading without data', async () => {
    useCurrentUserMock.mockReturnValue({ id: 'user-8' });
    // Make upcoming resolve quickly, but never resolve history
    queryFnMock.mockReturnValue(() => new Promise(() => { /* never resolves */ }));
    getRecentSearchesMock.mockResolvedValueOnce({ data: [], status: 200 });
    getTopServicesMock.mockResolvedValueOnce({ data: { categories: [] }, status: 200 });
    convertApiResponseMock.mockImplementation((response) => response.data);
    httpJsonMock.mockImplementation(() => new Promise(() => { /* never resolves */ }));

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useHomepageData(), { wrapper });

    // While queries are still loading, isAnyLoading should be true
    // isInitialLoading should also be true because some queries have no data yet
    expect(result.current.isAnyLoading).toBe(true);
    expect(result.current.isInitialLoading).toBe(true);
  });
});
