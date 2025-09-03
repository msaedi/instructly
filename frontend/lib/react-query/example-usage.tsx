/* eslint-disable @typescript-eslint/no-explicit-any -- Example file with intentionally loose types *//**
 * React Query Usage Examples for InstaInstru
 *
 * This file demonstrates how to use the React Query foundation
 * we've just implemented. These patterns should be followed
 * throughout the application.
 */

import React from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { useUser, useIsAuthenticated } from '@/hooks/queries/useUser';
import { useAuth } from '@/hooks/queries/useAuth';
import { queryFn, mutationFn } from '@/lib/react-query/api';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { requireString } from '@/lib/ts/safe';
import { publicApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';

/**
 * Example 1: Using the useUser hook in a component
 */
function UserProfileHeader() {
  const { data: user, isLoading, error } = useUser();

  if (isLoading) return <div>Loading user...</div>;
  if (error) return <div>Error loading user</div>;
  if (!user) return null;

  return (
    <div className="flex items-center gap-4">
      <div className="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center text-white">
        {user.first_name[0]}
      </div>
      <div>
        <h2>{user.first_name} {user.last_name}</h2>
        <p>{user.email}</p>
      </div>
    </div>
  );
}

/**
 * Example 2: Protected route with authentication check
 */
function ProtectedDashboard() {
  const { isAuthenticated, isLoading, user } = useIsAuthenticated();

  if (isLoading) return <div>Checking authentication...</div>;
  if (!isAuthenticated) {
    // Redirect to login or show login prompt
    return <div>Please log in to continue</div>;
  }

  return <div>Welcome to your dashboard, {user?.first_name}!</div>;
}

/**
 * Example 3: Search instructors with caching
 */
function InstructorSearch() {
  const searchQuery = 'yoga';

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.instructors.search({ query: searchQuery }),
    queryFn: async () => {
      const response = await publicApi.searchWithNaturalLanguage(searchQuery);
      if (response.error) throw new Error(response.error);
      return response.data;
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    gcTime: CACHE_TIMES.SLOW, // 15 minutes
  });

  if (isLoading) return <div>Searching...</div>;
  if (error) return <div>Search failed</div>;

  return (
    <div>
      <h3>Found {data?.total_found} instructors</h3>
      {data?.results.map((result) => (
        <div key={result.instructor.id}>
          {result.instructor.first_name} {result.instructor.last_initial}. - ${result.offering.hourly_rate}/hr
        </div>
      ))}
    </div>
  );
}

/**
 * Example 4: Instructor availability with real-time updates
 */
function InstructorAvailability({ instructorId }: { instructorId: string }) {
  const today = new Date().toISOString().split('T')[0];
  const nextWeek = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

  useQuery({
    queryKey: queryKeys.instructors.availability(instructorId, today),
    queryFn: () => {
      requireString(instructorId, 'instructorId');
      requireString(today, 'today');
      requireString(nextWeek, 'nextWeek');
      return queryFn(`/api/public/instructors/${instructorId}/availability`, {
        params: { start_date: today, end_date: nextWeek },
      });
    },
    staleTime: CACHE_TIMES.REALTIME, // 1 minute for real-time data
    refetchInterval: 60000, // Refetch every minute for live updates
  });

  return (
    <div>
      <h3>Available Slots</h3>
      {/* Render availability calendar */}
    </div>
  );
}

/**
 * Example 5: Creating a booking with optimistic updates
 */
function BookingForm({ instructorId, serviceId }: any) {
  const queryClient = useQueryClient();

  const createBookingMutation = useMutation<any, Error, any, { previousBookings?: any }>({
    mutationFn: mutationFn('/bookings', {
      method: 'POST',
      requireAuth: true,
    }),
    onMutate: async (newBooking: any) => {
      // Cancel ongoing queries
      await queryClient.cancelQueries({ queryKey: queryKeys.bookings.all });

      // Snapshot previous value
      const previousBookings = queryClient.getQueryData(queryKeys.bookings.all);

      // Optimistically update
      queryClient.setQueryData(queryKeys.bookings.all, (old: any) => {
        return [...(old || []), { ...newBooking, id: 'temp-id', status: 'pending' }];
      });

      return { previousBookings };
    },
    onError: (_, __, context) => {
      // Rollback on error
      queryClient.setQueryData(queryKeys.bookings.all, context?.previousBookings);
    },
    onSettled: () => {
      // Refetch after mutation
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
    },
  });

  const handleSubmit = async (formData: any) => {
    try {
      await createBookingMutation.mutateAsync({
        instructor_id: instructorId,
        service_id: serviceId,
        ...formData,
      });
      // Success! Redirect to confirmation
    } catch {
      // Error handled by mutation
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Form fields */}
      <button type="submit" disabled={createBookingMutation.isPending}>
        {createBookingMutation.isPending ? 'Booking...' : 'Book Now'}
      </button>
    </form>
  );
}

/**
 * Example 6: Infinite scroll for search results
 */
function InfiniteInstructorList() {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: queryKeys.instructors.all,
    queryFn: ({ pageParam = 0 }) =>
      queryFn('/instructors', {
        params: { offset: pageParam as number, limit: 20 },
      }),
    getNextPageParam: (lastPage: any, pages) => {
      const totalFetched = pages.length * 20;
      return totalFetched < lastPage.total ? totalFetched : undefined;
    },
    initialPageParam: 0,
    staleTime: CACHE_TIMES.SLOW,
  });

  return (
    <div>
      {data?.pages.map((page, i) => (
        <div key={i}>
          {page.instructors.map((instructor: any) => (
            <div key={instructor.id}>{instructor.user.full_name}</div>
          ))}
        </div>
      ))}

      {hasNextPage && (
        <button onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? 'Loading more...' : 'Load More'}
        </button>
      )}
    </div>
  );
}

/**
 * Example 7: Prefetching data for better UX
 */
function InstructorCard({ instructor }: any) {
  const queryClient = useQueryClient();

  // Prefetch instructor details on hover
  const handleMouseEnter = () => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.instructors.detail(instructor.id),
      queryFn: queryFn(`/instructors/${instructor.id}`),
      staleTime: CACHE_TIMES.SLOW,
    });
  };

  return (
    <div onMouseEnter={handleMouseEnter}>
      <h3>{instructor.name}</h3>
      {/* Card content */}
    </div>
  );
}

/**
 * Example 8: Login flow with React Query
 */
function LoginForm() {
  const { login, isLoggingIn, loginError } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);

    try {
      await login({
        email: formData.get('email') as string,
        password: formData.get('password') as string,
      });

      // Success! Redirect to dashboard
      router.push('/student/dashboard');
    } catch (error) {
      // Error is handled by the hook
      logger.error('Login failed', error as Error);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input name="email" type="email" required />
      <input name="password" type="password" required />

      {loginError && <div className="text-red-500">{loginError}</div>}

      <button type="submit" disabled={isLoggingIn}>
        {isLoggingIn ? 'Logging in...' : 'Log In'}
      </button>
    </form>
  );
}

export {
  UserProfileHeader,
  ProtectedDashboard,
  InstructorSearch,
  InstructorAvailability,
  BookingForm,
  InfiniteInstructorList,
  InstructorCard,
  LoginForm,
};
