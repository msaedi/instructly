jest.mock('@/features/shared/api/http', () => ({
  httpJson: jest.fn(),
}));

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getCatalogServices: jest.fn(),
  },
}));

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useInstructorProfile } from '../hooks/useInstructorProfile';
import { httpJson } from '@/features/shared/api/http';
import { publicApi } from '@/features/shared/api/client';

describe('useInstructorProfile fetch behaviour', () => {
  const createClient = () => new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
    },
  });

  const wrapper = ({ children }: { children: ReactNode }) => {
    const client = createClient();
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('uses relative endpoints via httpJson and catalog client', async () => {
    const mockInstructor = { user_id: 'me', services: [] };
    (httpJson as jest.Mock).mockResolvedValue(mockInstructor);
    (publicApi.getCatalogServices as jest.Mock).mockResolvedValue({ status: 200, data: [] });

    const { result } = renderHook(() => useInstructorProfile('me'), { wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(httpJson).toHaveBeenCalledTimes(1);
    const [urlArg, initArg] = (httpJson as jest.Mock).mock.calls[0];
    expect(urlArg).toBe('/instructors/me');
    expect((initArg as RequestInit)?.method).toBe('GET');
    expect(publicApi.getCatalogServices).toHaveBeenCalledTimes(1);
  });
});
