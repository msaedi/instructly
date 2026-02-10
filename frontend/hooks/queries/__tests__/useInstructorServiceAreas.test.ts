import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useInstructorServiceAreas } from '../useInstructorServiceAreas';
import { fetchWithAuth } from '@/lib/api';

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return {
    ...actual,
    fetchWithAuth: jest.fn(),
  };
});

const fetchWithAuthMock = fetchWithAuth as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper };
};

describe('useInstructorServiceAreas', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('returns service areas on successful fetch', async () => {
    const serviceAreasData = {
      service_areas: [
        { id: 'sa-1', name: 'Manhattan', neighborhoods: [] },
      ],
    };
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue(serviceAreasData),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInstructorServiceAreas(true), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(serviceAreasData);
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/addresses/service-areas/me');
  });

  it('throws when response is not ok', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: jest.fn().mockResolvedValue({ detail: 'Internal error' }),
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInstructorServiceAreas(true), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed to load service areas');
  });

  it('does not fetch when disabled', async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useInstructorServiceAreas(false), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toBeUndefined();
    expect(fetchWithAuthMock).not.toHaveBeenCalled();
  });
});
