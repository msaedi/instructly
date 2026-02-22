import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useInstructorProfile } from '../useInstructorProfile';
import { useInstructor } from '@/src/api/services/instructors';

jest.mock('@/src/api/services/instructors', () => ({
  useInstructor: jest.fn(),
}));

const mockUseInstructor = useInstructor as jest.Mock;

describe('useInstructorProfile', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    jest.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it('returns undefined when no data is available', () => {
    mockUseInstructor.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('test-id'), { wrapper });

    expect(result.current.data).toBeUndefined();
    expect(result.current.isLoading).toBe(true);
  });

  it('transforms basic instructor data correctly', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        id: '01K2TEST00000000000000001',
        user_id: '01K2TEST00000000000000001',
        bio: 'Test bio',
        years_experience: 5,
        user: {
          first_name: 'John',
          last_initial: 'D',
          has_profile_picture: true,
          profile_picture_version: 3,
        },
        services: [],
        service_area_boroughs: ['Manhattan'],
        service_area_neighborhoods: [{ neighborhood_id: 'n1', name: 'SoHo' }],
        service_area_summary: 'NYC area',
        favorited_count: 10,
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(result.current.data?.bio).toBe('Test bio');
    expect(result.current.data?.years_experience).toBe(5);
    expect(result.current.data?.user.first_name).toBe('John');
    expect(result.current.data?.user.last_initial).toBe('D');
    expect(result.current.data?.user.has_profile_picture).toBe(true);
    expect(result.current.data?.user.profile_picture_version).toBe(3);
    expect(result.current.data?.service_area_boroughs).toEqual(['Manhattan']);
    expect(result.current.data?.favorited_count).toBe(10);
  });

  it('maps services with all optional fields', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-1',
            service_catalog_id: 'cat-1',
            service_catalog_name: 'Piano',
            skill: 'Piano Lessons',
            hourly_rate: '75.00',
            duration_options: [30, 60, 90],
            description: 'Learn piano',
            location_types: ['in_person', 'online'],
            levels_taught: ['beginner', 'intermediate'],
            age_groups: ['kids', 'adults'],
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    expect(service?.id).toBe('svc-1');
    expect(service?.service_catalog_id).toBe('cat-1');
    expect(service?.service_catalog_name).toBe('Piano');
    expect(service?.skill).toBe('Piano Lessons');
    expect(service?.hourly_rate).toBe(75);
    expect(service?.duration_options).toEqual([30, 60, 90]);
    expect(service?.description).toBe('Learn piano');
    expect(service?.location_types).toEqual(['in_person', 'online']);
    expect(service?.levels_taught).toEqual(['beginner', 'intermediate']);
    expect(service?.age_groups).toEqual(['kids', 'adults']);
  });

  it('handles services without optional arrays', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-1',
            hourly_rate: 50,
            // No location_types, levels_taught, or age_groups
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    expect(service?.location_types).toBeUndefined();
    expect(service?.levels_taught).toBeUndefined();
    expect(service?.age_groups).toBeUndefined();
  });

  it('maps preferred_teaching_locations correctly', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_teaching_locations: [
          { address: '123 Main St', label: 'Home Studio' },
          { address: '456 Park Ave' }, // No label
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_teaching_locations).toBeDefined();
    });

    expect(result.current.data?.preferred_teaching_locations).toEqual([
      { address: '123 Main St', label: 'Home Studio' },
      { address: '456 Park Ave' },
    ]);
  });

  it('filters out invalid teaching locations', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_teaching_locations: [
          { address: '123 Main St' },
          { address: '  ' }, // Empty address
          { address: null }, // Null address
          null, // Null entry
          { address: '' }, // Empty string
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_teaching_locations).toBeDefined();
    });

    expect(result.current.data?.preferred_teaching_locations).toEqual([
      { address: '123 Main St' },
    ]);
  });

  it('maps preferred_public_spaces correctly', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_public_spaces: [
          { address: 'Central Park', label: 'Park' },
          { address: 'Library' }, // No label
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_public_spaces).toBeDefined();
    });

    expect(result.current.data?.preferred_public_spaces).toEqual([
      { address: 'Central Park', label: 'Park' },
      { address: 'Library' },
    ]);
  });

  it('filters out invalid public spaces', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_public_spaces: [
          { address: 'Central Park' },
          { address: '' }, // Empty string
          null, // Null entry
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_public_spaces).toBeDefined();
    });

    expect(result.current.data?.preferred_public_spaces).toEqual([
      { address: 'Central Park' },
    ]);
  });

  it('handles optional boolean fields correctly', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        verified: true,
        is_favorited: true,
        bgc_status: 'passed',
        bgc_completed_at: '2024-01-01T00:00:00Z',
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(result.current.data?.is_verified).toBe(true);
    expect(result.current.data?.is_favorited).toBe(true);
    expect((result.current.data as unknown as { bgc_status: string })?.bgc_status).toBe('passed');
    expect((result.current.data as unknown as { bgc_completed_at: string })?.bgc_completed_at).toBe('2024-01-01T00:00:00Z');
  });

  it('handles missing user object with default values', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        // No user object
        services: [],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(result.current.data?.user.first_name).toBe('Unknown');
    expect(result.current.data?.user.last_initial).toBe('');
  });

  it('handles top-level profile picture fields', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        has_profile_picture: true,
        profile_picture_version: 5,
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect((result.current.data as unknown as { has_profile_picture: boolean })?.has_profile_picture).toBe(true);
    expect((result.current.data as unknown as { profile_picture_version: number })?.profile_picture_version).toBe(5);
  });

  it('uses instructorId as fallback when id is missing', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        // No id field
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    expect(result.current.data?.id).toBe('01K2TEST00000000000000001');
  });

  it('handles services with name instead of skill', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-1',
            name: 'Guitar Lessons',
            hourly_rate: 60,
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    expect(service?.service_catalog_name).toBe('Guitar Lessons');
    expect(service?.skill).toBe('Guitar Lessons');
  });

  it('handles services with empty duration_options', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-1',
            hourly_rate: 60,
            duration_options: [],
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    // Default to [60] when empty
    expect(service?.duration_options).toEqual([60]);
  });

  it('maps service boolean flags offers_travel, offers_at_location, offers_online', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-flags',
            hourly_rate: 60,
            offers_travel: true,
            offers_at_location: true,
            offers_online: true,
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    expect(service?.offers_travel).toBe(true);
    expect(service?.offers_at_location).toBe(true);
    expect(service?.offers_online).toBe(true);
  });

  it('omits boolean flags when they are not booleans (e.g. undefined)', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-no-flags',
            hourly_rate: 60,
            // offers_travel, offers_at_location, offers_online are all undefined
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    expect(service?.offers_travel).toBeUndefined();
    expect(service?.offers_at_location).toBeUndefined();
    expect(service?.offers_online).toBeUndefined();
  });

  it('maps preferred_teaching_locations with approx_lat and approx_lng', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_teaching_locations: [
          {
            address: '123 Broadway',
            label: 'Studio',
            approx_lat: 40.7128,
            approx_lng: -74.006,
            neighborhood: 'FiDi',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_teaching_locations).toBeDefined();
    });

    const loc = result.current.data?.preferred_teaching_locations?.[0] as {
      address?: string;
      label?: string;
      approx_lat?: number;
      approx_lng?: number;
      neighborhood?: string;
    } | undefined;
    expect(loc?.address).toBe('123 Broadway');
    expect(loc?.label).toBe('Studio');
    expect(loc?.approx_lat).toBe(40.7128);
    expect(loc?.approx_lng).toBe(-74.006);
    expect(loc?.neighborhood).toBe('FiDi');
  });

  it('omits approx_lat/lng when they are not numbers', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_teaching_locations: [
          {
            address: '456 Park Ave',
            approx_lat: 'not-a-number' as unknown,
            approx_lng: null as unknown,
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_teaching_locations).toBeDefined();
    });

    const loc = result.current.data?.preferred_teaching_locations?.[0] as {
      address?: string;
      approx_lat?: number;
      approx_lng?: number;
    } | undefined;
    expect(loc?.address).toBe('456 Park Ave');
    // Non-numeric values should be omitted
    expect(loc?.approx_lat).toBeUndefined();
    expect(loc?.approx_lng).toBeUndefined();
  });

  it('keeps location with only neighborhood set', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_teaching_locations: [
          {
            neighborhood: 'SoHo',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_teaching_locations).toBeDefined();
    });

    const loc = result.current.data?.preferred_teaching_locations?.[0] as {
      neighborhood?: string;
    } | undefined;
    expect(loc?.neighborhood).toBe('SoHo');
  });

  it('maps background_check_status as bgc_status fallback', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        background_check_status: 'clear',
        background_check_verified: true,
        background_check_completed: true,
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    const profile = result.current.data as unknown as { bgc_status?: string; background_check_completed?: boolean };
    expect(profile?.bgc_status).toBe('clear');
    expect(profile?.background_check_completed).toBe(true);
  });

  it('handles NaN hourly_rate', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-1',
            hourly_rate: 'invalid',
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    // Default to 0 when NaN
    expect(service?.hourly_rate).toBe(0);
  });

  it('falls back to instructorId when both id and user_id are missing', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        // No id field, no user_id
        user_id: '',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('fallback-instructor-id'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // canonicalId falls through: id is not a string -> user_id is '' (falsy) -> instructorId
    expect(result.current.data?.id).toBe('fallback-instructor-id');
    // user_id also falls through to canonicalId
    expect(result.current.data?.user_id).toBe('fallback-instructor-id');
  });

  it('maps service with numeric hourly_rate directly', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-num',
            hourly_rate: 99.5,
            duration_options: [45],
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    expect(service?.hourly_rate).toBe(99.5);
    expect(service?.duration_options).toEqual([45]);
  });

  it('maps is_live and is_founding_instructor when set to false', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        is_live: false,
        is_founding_instructor: false,
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // Boolean false should still be included via the typeof check
    expect((result.current.data as unknown as { is_live?: boolean })?.is_live).toBe(false);
    expect((result.current.data as unknown as { is_founding_instructor?: boolean })?.is_founding_instructor).toBe(false);
  });

  it('handles preferred_public_spaces with label field', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_public_spaces: [
          { address: 'Prospect Park', label: 'Fave spot' },
          { address: 'Bryant Park', label: '  ' }, // Whitespace-only label
          { address: 'Union Square' }, // No label
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_public_spaces).toBeDefined();
    });

    const spaces = result.current.data?.preferred_public_spaces;
    expect(spaces).toEqual([
      { address: 'Prospect Park', label: 'Fave spot' },
      { address: 'Bryant Park' }, // Whitespace label trimmed to empty -> omitted
      { address: 'Union Square' },
    ]);
  });

  it('omits service_area_summary as null when undefined', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        // service_area_summary intentionally absent
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // undefined ?? null = null
    expect(result.current.data?.service_area_summary).toBeNull();
  });

  it('handles preferred_public_spaces with non-string label', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [],
        preferred_public_spaces: [
          { address: 'Central Park', label: 42 }, // Non-string label -> omitted
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.preferred_public_spaces).toBeDefined();
    });

    // Non-string label falls to '' in ternary, so label is not included
    expect(result.current.data?.preferred_public_spaces).toEqual([
      { address: 'Central Park' },
    ]);
  });

  it('maps service with null hourly_rate to 0', async () => {
    mockUseInstructor.mockReturnValue({
      data: {
        user_id: '01K2TEST00000000000000001',
        user: { first_name: 'Test', last_initial: 'U' },
        services: [
          {
            id: 'svc-null-rate',
            hourly_rate: null,
            duration_options: undefined,
          },
        ],
      },
      isLoading: false,
      error: null,
    });

    const { result } = renderHook(() => useInstructorProfile('01K2TEST00000000000000001'), { wrapper });

    await waitFor(() => {
      expect(result.current.data?.services).toBeDefined();
    });

    const service = result.current.data?.services[0];
    // null -> parseFloat('0') = 0 and NaN check passes -> 0
    expect(service?.hourly_rate).toBe(0);
    // undefined duration_options -> [60]
    expect(service?.duration_options).toEqual([60]);
  });
});
