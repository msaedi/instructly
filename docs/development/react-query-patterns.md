# React Query Patterns for InstaInstru

## When to Use React Query (Answer: ALWAYS for API calls)

### Pages That MUST Have Caching
1. **Homepage** ✅ - Featured services, user data
2. **Services Browse** ✅ - Categories, service lists
3. **Search Results** - Query results, filters
4. **Instructor Profiles** - Profile data, availability preview
5. **Student Dashboard** - Bookings, history
6. **Instructor Dashboard** - Stats, bookings

### Data-Specific Caching Strategy
| Data Type | Cache Time | Background Refetch | Example |
|-----------|------------|-------------------|---------|
| User Profile | Infinity | No | Name, email, preferences |
| Categories | 1 hour | No | Music, Tutoring, etc. |
| Services | 15-60 min | No | Service listings |
| Search Results | 5 min | No | Instructor search |
| Availability | 5 min | Yes | Time slots |
| Bookings | 5 min | Yes | Upcoming lessons |
| Notifications | 1 min | Yes | New messages |

### Implementation Checklist for New Pages
- [ ] Import React Query hooks
- [ ] Replace ALL fetch() with useQuery
- [ ] Include proper query keys with params
- [ ] Set appropriate stale time
- [ ] Handle loading and error states
- [ ] Test caching in DevTools

## Core Patterns

### 1. Basic Query Pattern
```typescript
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';

export function useInstructorProfile(instructorId: string) {
  return useQuery({
    queryKey: queryKeys.instructors.detail(instructorId),
    queryFn: () => publicApi.getInstructorProfile(instructorId),
    staleTime: 1000 * 60 * 15, // 15 minutes
    gcTime: 1000 * 60 * 30, // 30 minutes
  });
}
```

### 2. Authenticated Query Pattern
```typescript
export function useMyBookings() {
  const { data: user } = useUser();

  return useQuery({
    queryKey: queryKeys.bookings.list(),
    queryFn: queryFn('/bookings/', { requireAuth: true }),
    enabled: !!user, // Only run if authenticated
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}
```

### 3. Dependent Query Pattern
```typescript
export function useInstructorAvailability(instructorId: string, date: string) {
  const { data: instructor } = useInstructorProfile(instructorId);

  return useQuery({
    queryKey: queryKeys.availability.byInstructor(instructorId, date),
    queryFn: () => publicApi.getInstructorAvailability(instructorId, date),
    enabled: !!instructor && instructor.is_active, // Only if instructor exists and active
    staleTime: 1000 * 60 * 5, // 5 minutes - availability changes frequently
    refetchInterval: 1000 * 60 * 5, // Refetch every 5 minutes
  });
}
```

### 4. Mutation Pattern
```typescript
export function useCreateBooking() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateBookingRequest) => api.createBooking(data),
    onSuccess: (booking) => {
      // Invalidate and refetch related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.availability.byInstructor(booking.instructor_id)
      });

      // Optionally update cache directly
      queryClient.setQueryData(
        queryKeys.bookings.detail(booking.id),
        booking
      );
    },
  });
}
```

### 5. Parallel Queries Pattern
```typescript
export function useDashboardData() {
  const queries = useQueries({
    queries: [
      {
        queryKey: queryKeys.user.current,
        queryFn: queryFn('/auth/me'),
        staleTime: Infinity, // User data rarely changes
      },
      {
        queryKey: queryKeys.bookings.upcoming,
        queryFn: queryFn('/bookings/upcoming'),
        staleTime: 1000 * 60 * 5,
      },
      {
        queryKey: queryKeys.stats.overview,
        queryFn: queryFn('/stats/overview'),
        staleTime: 1000 * 60 * 15,
      },
    ],
  });

  return {
    user: queries[0].data,
    upcomingBookings: queries[1].data,
    stats: queries[2].data,
    isLoading: queries.some(q => q.isLoading),
  };
}
```

### 6. Infinite Query Pattern
```typescript
export function useInstructorSearch(filters: SearchFilters) {
  return useInfiniteQuery({
    queryKey: queryKeys.instructors.search(filters),
    queryFn: ({ pageParam = 1 }) =>
      publicApi.searchInstructors({ ...filters, page: pageParam }),
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.current_page + 1 : undefined,
    staleTime: 1000 * 60 * 5,
    initialPageParam: 1,
  });
}
```

### 7. Prefetching Pattern
```typescript
export function usePrefetchInstructor(instructorId: string) {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.prefetchQuery({
      queryKey: queryKeys.instructors.detail(instructorId),
      queryFn: () => publicApi.getInstructorProfile(instructorId),
      staleTime: 1000 * 60 * 15,
    });
  }, [queryClient, instructorId]);
}

// Usage in component
function InstructorCard({ instructor }) {
  const prefetch = usePrefetchInstructor(instructor.id);

  return (
    <Link
      href={`/instructors/${instructor.id}`}
      onMouseEnter={prefetch} // Prefetch on hover
    >
      {instructor.name}
    </Link>
  );
}
```

### 8. Optimistic Update Pattern
```typescript
export function useToggleFavorite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: api.toggleFavorite,
    onMutate: async (instructorId) => {
      // Cancel in-flight queries
      await queryClient.cancelQueries({
        queryKey: queryKeys.favorites.list()
      });

      // Snapshot previous value
      const previous = queryClient.getQueryData(queryKeys.favorites.list());

      // Optimistically update
      queryClient.setQueryData(queryKeys.favorites.list(), (old) => {
        return old.includes(instructorId)
          ? old.filter(id => id !== instructorId)
          : [...old, instructorId];
      });

      return { previous };
    },
    onError: (err, instructorId, context) => {
      // Rollback on error
      queryClient.setQueryData(
        queryKeys.favorites.list(),
        context.previous
      );
    },
    onSettled: () => {
      // Always refetch after mutation
      queryClient.invalidateQueries({
        queryKey: queryKeys.favorites.list()
      });
    },
  });
}
```

## Query Key Patterns

### Hierarchical Structure
```typescript
export const queryKeys = {
  all: ['instructly'] as const,

  instructors: {
    all: ['instructly', 'instructors'] as const,
    lists: () => [...queryKeys.instructors.all, 'list'] as const,
    list: (filters: any) => [...queryKeys.instructors.lists(), filters] as const,
    details: () => [...queryKeys.instructors.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.instructors.details(), id] as const,
    search: (query: string) => [...queryKeys.instructors.all, 'search', query] as const,
  },

  bookings: {
    all: ['instructly', 'bookings'] as const,
    upcoming: () => [...queryKeys.bookings.all, 'upcoming'] as const,
    history: () => [...queryKeys.bookings.all, 'history'] as const,
    detail: (id: string) => [...queryKeys.bookings.all, 'detail', id] as const,
  },

  availability: {
    all: ['instructly', 'availability'] as const,
    byInstructor: (instructorId: string, date?: string) =>
      date
        ? [...queryKeys.availability.all, instructorId, date] as const
        : [...queryKeys.availability.all, instructorId] as const,
  },
};
```

### Invalidation Patterns
```typescript
// Invalidate all instructor data
queryClient.invalidateQueries({ queryKey: queryKeys.instructors.all });

// Invalidate specific instructor
queryClient.invalidateQueries({
  queryKey: queryKeys.instructors.detail(instructorId)
});

// Invalidate all bookings
queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });

// Remove specific data from cache
queryClient.removeQueries({
  queryKey: queryKeys.availability.byInstructor(instructorId)
});
```

## Error Handling Patterns

### Global Error Boundary
```typescript
import { ErrorBoundary } from '@/components/ErrorBoundary';

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        {/* Your app */}
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
```

### Query-Level Error Handling
```typescript
export function useInstructorProfile(id: string) {
  const { data, error, isError } = useQuery({
    queryKey: queryKeys.instructors.detail(id),
    queryFn: () => publicApi.getInstructorProfile(id),
    retry: (failureCount, error) => {
      // Don't retry on 404s
      if (error.status === 404) return false;
      // Retry up to 3 times for other errors
      return failureCount < 3;
    },
  });

  if (isError) {
    if (error.status === 404) {
      return { notFound: true };
    }
    throw error; // Let error boundary handle
  }

  return { data };
}
```

## Testing Patterns

### Mock Query Client
```typescript
import { QueryClient } from '@tanstack/react-query';

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
}
```

### Testing Hooks
```typescript
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';

test('useInstructorProfile fetches data', async () => {
  const queryClient = createTestQueryClient();

  const { result } = renderHook(
    () => useInstructorProfile('123'),
    {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      ),
    }
  );

  await waitFor(() => {
    expect(result.current.isSuccess).toBe(true);
  });

  expect(result.current.data).toEqual(mockInstructor);
});
```

## Common Pitfalls to Avoid

### ❌ Don't: Manual State Management
```typescript
// BAD
const [instructors, setInstructors] = useState([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState(null);

useEffect(() => {
  setLoading(true);
  fetch('/api/instructors')
    .then(res => res.json())
    .then(data => setInstructors(data))
    .catch(err => setError(err))
    .finally(() => setLoading(false));
}, []);
```

### ✅ Do: Use React Query
```typescript
// GOOD
const { data: instructors, isLoading, error } = useQuery({
  queryKey: queryKeys.instructors.list(),
  queryFn: () => publicApi.getInstructors(),
});
```

### ❌ Don't: Inconsistent Query Keys
```typescript
// BAD - Different key structures
useQuery({ queryKey: ['instructor', id] });
useQuery({ queryKey: ['instructors', 'detail', id] });
```

### ✅ Do: Use Consistent Query Key Factory
```typescript
// GOOD - Consistent structure
useQuery({ queryKey: queryKeys.instructors.detail(id) });
```

### ❌ Don't: Forget to Handle Loading States
```typescript
// BAD
function InstructorList() {
  const { data } = useInstructors();

  return (
    <div>
      {data.map(instructor => <InstructorCard {...instructor} />)}
    </div>
  );
}
```

### ✅ Do: Handle All States
```typescript
// GOOD
function InstructorList() {
  const { data, isLoading, error } = useInstructors();

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorMessage error={error} />;
  if (!data?.length) return <EmptyState />;

  return (
    <div>
      {data.map(instructor => <InstructorCard {...instructor} />)}
    </div>
  );
}
```

## Migration Guide

### Step 1: Identify API Calls
```typescript
// Look for these patterns:
- fetch() calls
- axios requests
- useEffect with async functions
- useState for loading/error states
```

### Step 2: Create Custom Hook
```typescript
// Before
useEffect(() => {
  fetch(`/api/instructors/${id}`)
    .then(res => res.json())
    .then(data => setInstructor(data));
}, [id]);

// After
const { data: instructor } = useInstructorProfile(id);
```

### Step 3: Remove State Management
```typescript
// Remove these:
- const [data, setData] = useState()
- const [loading, setLoading] = useState(false)
- const [error, setError] = useState(null)

// Replace with:
const { data, isLoading, error } = useQuery(...)
```

### Step 4: Update Component Logic
```typescript
// Before
if (loading) return <div>Loading...</div>;
if (error) return <div>Error: {error.message}</div>;

// After
if (isLoading) return <div>Loading...</div>;
if (error) return <div>Error: {error.message}</div>;
```

## Performance Tips

1. **Use Stale-While-Revalidate**: Show stale data immediately while fetching fresh data
2. **Prefetch on Hover**: Prefetch data when users hover over links
3. **Cache Sharing**: Use consistent query keys to share cache between components
4. **Background Refetching**: Keep data fresh without loading states
5. **Query Invalidation**: Invalidate smartly after mutations
6. **Suspense Mode**: Use React Suspense for cleaner loading states

## Debugging with React Query DevTools

In development, React Query DevTools are available at the bottom of the screen:

- **Red Badge**: Number of fetching queries
- **Green Badge**: Number of fresh queries
- **Yellow Badge**: Number of stale queries
- **Gray Badge**: Number of inactive queries

Click on any query to:
- View query key and data
- Manually refetch
- Invalidate cache
- Remove from cache
- View query details (stale time, cache time, etc.)
