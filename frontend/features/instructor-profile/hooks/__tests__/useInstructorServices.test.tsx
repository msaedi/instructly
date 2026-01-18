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
});
