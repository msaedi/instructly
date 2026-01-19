import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useInstructorServices } from '../useInstructorServices';
import { queryFn } from '@/lib/react-query/api';
import type { ReactNode } from 'react';

// Mock the queryFn
jest.mock('@/lib/react-query/api', () => ({
  queryFn: jest.fn(),
}));

const queryFnMock = queryFn as jest.Mock;

// Create wrapper with QueryClient
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return Wrapper;
};

describe('useInstructorServices', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches instructor services successfully', async () => {
    const mockServices = {
      services: [
        { id: 'svc-1', skill: 'Piano', hourly_rate: 60 },
        { id: 'svc-2', skill: 'Guitar', hourly_rate: 45 },
      ],
    };

    queryFnMock.mockReturnValue(() => Promise.resolve(mockServices));

    const { result } = renderHook(
      () => useInstructorServices('instructor-123'),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockServices);
  });

  it('calls queryFn with correct endpoint', async () => {
    const mockServices = { services: [] };
    queryFnMock.mockReturnValue(() => Promise.resolve(mockServices));

    renderHook(
      () => useInstructorServices('instructor-456'),
      { wrapper: createWrapper() }
    );

    expect(queryFnMock).toHaveBeenCalledWith(
      '/instructors/instructor-456/services',
      { requireAuth: false }
    );
  });

  it('does not fetch when instructorId is empty', async () => {
    const mockServices = { services: [] };
    queryFnMock.mockReturnValue(() => Promise.resolve(mockServices));

    const { result } = renderHook(
      () => useInstructorServices(''),
      { wrapper: createWrapper() }
    );

    // Query should be disabled
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isFetching).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  it('handles fetch error', async () => {
    const error = new Error('Failed to fetch services');
    queryFnMock.mockReturnValue(() => Promise.reject(error));

    const { result } = renderHook(
      () => useInstructorServices('instructor-error'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeDefined();
  });

  it('uses correct query key structure', async () => {
    const mockServices = { services: [] };
    queryFnMock.mockReturnValue(() => Promise.resolve(mockServices));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    renderHook(
      () => useInstructorServices('instructor-key'),
      { wrapper }
    );

    await waitFor(() => {
      const queries = queryClient.getQueryCache().findAll();
      expect(queries.length).toBeGreaterThan(0);
      const query = queries[0];
      expect(query?.queryKey).toEqual(['instructors', 'instructor-key', 'services']);
    });
  });

  it('returns loading state initially', () => {
    queryFnMock.mockReturnValue(() => new Promise(() => {})); // Never resolves

    const { result } = renderHook(
      () => useInstructorServices('instructor-loading'),
      { wrapper: createWrapper() }
    );

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it('handles empty services array response', async () => {
    const emptyResponse = { services: [] };
    queryFnMock.mockReturnValue(() => Promise.resolve(emptyResponse));

    const { result } = renderHook(
      () => useInstructorServices('instructor-empty'),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.services).toEqual([]);
  });

  it('does not refetch when instructorId changes from empty to valid', async () => {
    const mockServices = { services: [{ id: 'svc-1', skill: 'Piano' }] };
    queryFnMock.mockReturnValue(() => Promise.resolve(mockServices));

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useInstructorServices(id),
      {
        wrapper: createWrapper(),
        initialProps: { id: '' }
      }
    );

    // Initially disabled
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isFetching).toBe(false);

    // Update to valid ID
    rerender({ id: 'instructor-new' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockServices);
  });

  it('maintains cache across re-renders with same instructorId', async () => {
    const mockServices = { services: [{ id: 'svc-1', skill: 'Violin' }] };
    let callCount = 0;
    queryFnMock.mockReturnValue(() => {
      callCount++;
      return Promise.resolve(mockServices);
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 60000 } },
    });

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result, rerender } = renderHook(
      () => useInstructorServices('instructor-cache'),
      { wrapper }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Re-render should use cached data
    rerender();

    expect(result.current.data).toEqual(mockServices);
    // Should only have called once due to cache
    expect(callCount).toBe(1);
  });

  it('provides correct status flags during lifecycle', async () => {
    let resolvePromise: (value: unknown) => void;
    const slowPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    queryFnMock.mockReturnValue(() => slowPromise);

    const { result } = renderHook(
      () => useInstructorServices('instructor-lifecycle'),
      { wrapper: createWrapper() }
    );

    // Initially loading
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isFetching).toBe(true);
    expect(result.current.isSuccess).toBe(false);
    expect(result.current.isError).toBe(false);

    // Resolve the promise
    resolvePromise!({ services: [] });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // After success
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isFetching).toBe(false);
    expect(result.current.isError).toBe(false);
  });

  it('sets requireAuth to false for public endpoint', () => {
    queryFnMock.mockReturnValue(() => Promise.resolve({ services: [] }));

    renderHook(
      () => useInstructorServices('instructor-public'),
      { wrapper: createWrapper() }
    );

    // Verify requireAuth is false (public endpoint)
    const calls = queryFnMock.mock.calls;
    expect(calls[0][1]).toEqual({ requireAuth: false });
  });
});
