jest.mock('@/src/api/services/instructors', () => ({
  useInstructor: jest.fn(),
}));

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useInstructorProfile } from '../hooks/useInstructorProfile';
import { useInstructor } from '@/src/api/services/instructors';

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

  it('uses v1 instructor service and transforms response', async () => {
    const mockInstructor = {
      id: 'instructor-123',
      user_id: 'user-123',
      user: {
        first_name: 'John',
        last_initial: 'D',
        has_profile_picture: false,
      },
      bio: 'Test bio',
      services: [
        {
          id: 'svc-1',
          service_catalog_id: 'catalog-1',
          service_catalog_name: 'Yoga',
          hourly_rate: 60,
          duration_options: [60, 90],
          description: 'Test service',
        },
      ],
      service_area_boroughs: ['Manhattan'],
      service_area_neighborhoods: [],
      service_area_summary: 'Manhattan area',
      preferred_teaching_locations: [],
      preferred_public_spaces: [],
      years_experience: 5,
      favorited_count: 10,
    };

    (useInstructor as jest.Mock).mockReturnValue({
      data: mockInstructor,
      isLoading: false,
      isSuccess: true,
      isError: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('instructor-123'), { wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(useInstructor).toHaveBeenCalledWith('instructor-123');
    expect(result.current.data).toBeDefined();
    expect(result.current.data?.id).toBe('instructor-123');
    expect(result.current.data?.services).toHaveLength(1);
    expect(result.current.data?.services?.[0]?.service_catalog_name).toBe('Yoga');
  });
});
