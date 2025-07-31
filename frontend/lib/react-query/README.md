# React Query Implementation for InstaInstru

This directory contains the React Query foundation for the InstaInstru platform, providing intelligent client-side caching to improve user experience and reduce server load.

## Overview

React Query has been integrated to solve the following problems:
- Eliminate redundant API calls when navigating between pages
- Provide instant page transitions with cached data
- Enable optimistic updates for bookings
- Support background refetching for real-time availability
- Reduce API calls by 60-80%

## Core Files

### `/lib/react-query/queryClient.ts`
The main React Query configuration with marketplace-optimized defaults:
- 5-minute stale time for most data
- 30-minute garbage collection time (gcTime) for navigation
- Smart retry logic (skip 4xx, retry 5xx)
- Disabled window focus refetching

### `/lib/react-query/api.ts`
Integration utilities that wrap the existing API client:
- `queryFn()` - For queries with automatic auth and cancellation
- `mutationFn()` - For mutations with proper error handling
- `ApiError` class for consistent error types
- Helper functions for error detection

### `/lib/react-query/types.ts`
TypeScript types and utilities for type-safe React Query usage:
- Custom query/mutation option types
- Common response formats
- Type-safe query key builders
- Helper type guards

## Essential Hooks

### `useUser()` - Current User Data
```tsx
import { useUser } from '@/hooks/queries/useUser';

function Profile() {
  const { data: user, isLoading } = useUser();

  if (isLoading) return <Spinner />;
  return <div>Welcome {user?.full_name}</div>;
}
```

### `useAuth()` - Authentication Management
```tsx
import { useAuth } from '@/hooks/queries/useAuth';

function LoginPage() {
  const { login, isLoggingIn, logout } = useAuth();

  const handleLogin = async (email, password) => {
    await login({ email, password });
  };
}
```

### `useIsAuthenticated()` - Auth Status Check
```tsx
import { useIsAuthenticated } from '@/hooks/queries/useUser';

function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useIsAuthenticated();

  if (isLoading) return <LoadingScreen />;
  if (!isAuthenticated) return <Navigate to="/login" />;

  return children;
}
```

## Query Key Patterns

Use hierarchical, consistent query keys:

```tsx
// Good patterns from queryClient.ts
queryKeys.user                                    // ['user']
queryKeys.users.detail('123')                     // ['users', '123']
queryKeys.bookings.upcoming                       // ['bookings', 'upcoming']
queryKeys.instructors.availability('123', '2024-01-01') // ['instructors', '123', 'availability', '2024-01-01']
```

## Cache Time Guidelines

```tsx
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

// Session-long data (user profile, settings)
staleTime: CACHE_TIMES.SESSION      // Infinity

// Frequently changing (availability, bookings)
staleTime: CACHE_TIMES.FREQUENT      // 5 minutes

// Slowly changing (instructor profiles)
staleTime: CACHE_TIMES.SLOW          // 15 minutes

// Real-time critical (current slots)
staleTime: CACHE_TIMES.REALTIME      // 1 minute

// Static data (categories)
staleTime: CACHE_TIMES.STATIC        // 1 hour
```

## Usage Examples

### Basic Query
```tsx
const { data: instructors } = useQuery({
  queryKey: queryKeys.instructors.all,
  queryFn: queryFn('/instructors'),
  staleTime: CACHE_TIMES.SLOW,
});
```

### Query with Parameters
```tsx
const { data: availability } = useQuery({
  queryKey: queryKeys.instructors.availability(instructorId, date),
  queryFn: queryFn(`/api/public/instructors/${instructorId}/availability`, {
    params: { start_date, end_date },
  }),
  staleTime: CACHE_TIMES.REALTIME,
});
```

### Mutation with Optimistic Updates
```tsx
const createBooking = useMutation({
  mutationFn: mutationFn('/bookings', { method: 'POST', requireAuth: true }),
  onMutate: async (newBooking) => {
    // Optimistically update UI
    await queryClient.cancelQueries(queryKeys.bookings.upcoming);
    const previous = queryClient.getQueryData(queryKeys.bookings.upcoming);
    queryClient.setQueryData(queryKeys.bookings.upcoming, old => [...old, newBooking]);
    return { previous };
  },
  onError: (err, newBooking, context) => {
    // Rollback on error
    queryClient.setQueryData(queryKeys.bookings.upcoming, context.previous);
  },
  onSettled: () => {
    // Refetch to ensure consistency
    queryClient.invalidateQueries(queryKeys.bookings.upcoming);
  },
});
```

### Prefetching
```tsx
// Prefetch on hover for instant navigation
const handleHover = () => {
  queryClient.prefetchQuery({
    queryKey: queryKeys.instructors.detail(instructorId),
    queryFn: queryFn(`/instructors/${instructorId}`),
    staleTime: CACHE_TIMES.SLOW,
  });
};
```

## Error Handling

### Error Boundary
Wrap components that should show error UI:
```tsx
import { QueryErrorBoundary } from '@/components/errors/QueryErrorBoundary';

<QueryErrorBoundary>
  <YourComponent />
</QueryErrorBoundary>
```

### Inline Error Handling
For components that handle errors themselves:
```tsx
const { data, error } = useQuery({
  queryKey: ['data'],
  queryFn: fetchData,
  useErrorBoundary: false, // Don't throw to error boundary
});

if (error) return <ErrorMessage error={error} />;
```

## DevTools

React Query DevTools are available in development at the bottom-right corner. Use them to:
- Inspect cache contents
- Manually trigger refetches
- Clear cache for testing
- Monitor query states

## Migration Guide

When migrating existing components:

1. **Replace fetch calls with queries:**
   ```tsx
   // Before
   useEffect(() => {
     fetch('/api/user').then(res => res.json()).then(setUser);
   }, []);

   // After
   const { data: user } = useUser();
   ```

2. **Replace manual loading states:**
   ```tsx
   // Before
   const [loading, setLoading] = useState(true);
   const [data, setData] = useState(null);

   // After
   const { data, isLoading } = useQuery({...});
   ```

3. **Use mutations for updates:**
   ```tsx
   // Before
   const handleSubmit = async (data) => {
     setLoading(true);
     try {
       await fetch('/api/bookings', { method: 'POST', body: data });
       // manual state update
     } catch (error) {
       // error handling
     } finally {
       setLoading(false);
     }
   };

   // After
   const mutation = useMutation({...});
   const handleSubmit = (data) => mutation.mutate(data);
   ```

## Best Practices

1. **Always use query keys from the factory** - Don't hardcode query keys
2. **Set appropriate stale times** - Use CACHE_TIMES constants
3. **Handle loading and error states** - Every query needs UI feedback
4. **Prefetch on hover** - For better perceived performance
5. **Use optimistic updates** - For instant UI feedback
6. **Invalidate related queries** - Keep cache consistent
7. **Don't over-cache** - Real-time data needs short stale times

## Next Steps

With this foundation in place, the next priorities are:

1. Migrate homepage queries to React Query
2. Implement infinite scroll for instructor search
3. Add optimistic booking creation
4. Set up background refetching for availability

See `example-usage.tsx` for implementation patterns.
