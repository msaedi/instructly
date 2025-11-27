# API Call Deduplication Migration Plan

> **Created**: 2025-11-27
> **Status**: In Progress
> **Goal**: Eliminate duplicate API calls causing 429 rate limit errors

## Executive Summary

The frontend has multiple places fetching the same data independently, causing:
- 429 "Too Many Requests" errors
- Unnecessary server load
- Poor user experience (loading states, failed operations)

**Solution**: Migrate from direct `fetchWithAuth` calls to React Query hooks, which share a global cache.

---

## Architecture Overview

### Current Data Fetching Patterns

| Pattern | Description | Cache? | Problem |
|---------|-------------|--------|---------|
| `fetchWithAuth` in `useEffect` | Direct fetch on mount | No | Duplicates on every mount |
| React Query hooks (`useXxx`) | Declarative data fetching | Yes (15min stale) | None - this is the target |
| Prop drilling | Pass data from parent | N/A | Good for child components |

### React Query Cache Behavior
- **staleTime: 15 minutes** - Data considered fresh, no refetch
- **Global cache** - All components share the same data
- **Automatic deduplication** - Concurrent requests merged into one

---

## Endpoints Requiring Migration

### 1. `/api/v1/instructors/me` (Instructor Profile)

**React Query Hook**: `useInstructorProfileMe` from `@/hooks/queries/useInstructorProfileMe`

| File | Line | Type | Status | Notes |
|------|------|------|--------|-------|
| `app/(auth)/instructor/dashboard/page.tsx` | 350 | READ | ✅ Done | Uses hook |
| `features/instructor-profile/InstructorProfileForm.tsx` | 152 | READ | ✅ Done | Uses hook |
| `components/UserProfileDropdown.tsx` | 29 | READ | ✅ Done | Uses hook with skip |
| `components/instructor/ProgressSteps.tsx` | 22 | READ | ⚠️ TODO | Needs hook |
| `components/modals/EditProfileModal.tsx` | 274, 480 | READ | ⚠️ TODO | Needs hook or prop |
| `app/dashboard/instructor/page.tsx` | 78 | READ | 🔍 Check | Old dashboard? |
| `features/instructor-onboarding/useOnboardingStepStatus.ts` | 70 | READ | ✅ OK | Unified hook (intentional) |
| `app/(auth)/instructor/onboarding/status/page.tsx` | 141 | READ | ✅ OK | Uses unified hook |
| `features/instructor-profile/SkillsPricingInline.tsx` | 123 | READ | ✅ Done | Conditional with prop |

**WRITE operations (keep as fetchWithAuth):**
- `InstructorProfileForm.tsx:555` - PUT save profile
- `SkillsPricingInline.tsx:349` - PUT save services
- `EditProfileModal.tsx:739, 853, 1006` - PUT operations
- `DeleteProfileModal.tsx:52` - DELETE operation
- `skill-selection/page.tsx:247, 284` - PUT save skills

### 2. `/api/v1/auth/me` (Current User)

**React Query Hook**: Need to check if exists or create one

| File | Pattern | Status | Notes |
|------|---------|--------|-------|
| `InstructorProfileForm.tsx` | `fetchWithAuth(API_ENDPOINTS.ME)` | ⚠️ TODO | Multiple calls |
| Auth context | Various | 🔍 Check | May already be cached |

### 3. `/api/v1/addresses/me` (User Addresses)

| File | Pattern | Status | Notes |
|------|---------|--------|-------|
| `InstructorProfileForm.tsx` | Multiple calls | ⚠️ TODO | Called twice in load() |

### 4. `/api/v1/addresses/service-areas/me` (Service Areas)

| File | Pattern | Status | Notes |
|------|---------|--------|-------|
| `InstructorProfileForm.tsx` | Called in load() | ⚠️ TODO | Duplicate on Strict Mode |
| Dashboard page | May also fetch | 🔍 Check | |

### 5. `/api/v1/payments/connect/status` (Stripe Connect Status)

| File | Pattern | Status | Notes |
|------|---------|--------|-------|
| Dashboard page | Direct fetch | 🔍 Check | May need hook |

### 6. `/api/v1/messages/unread-count` (Unread Messages)

| File | Pattern | Status | Notes |
|------|---------|--------|-------|
| Multiple components | Direct fetch | 🔍 Check | Should use single hook |

---

## Migration Priorities

### Priority 1: High Impact (Causing 429s)
1. ~~`InstructorProfileForm.tsx` - instructor profile~~ ✅ DONE
2. `ProgressSteps.tsx` - instructor profile
3. `EditProfileModal.tsx` - instructor profile on modal open

### Priority 2: Medium Impact (Redundant calls)
4. `/api/v1/auth/me` - create/use unified hook
5. `/api/v1/addresses/me` - dedupe in InstructorProfileForm
6. `/api/v1/addresses/service-areas/me` - dedupe

### Priority 3: Low Impact (Optimization)
7. `/api/v1/payments/connect/status` - consider caching
8. `/api/v1/messages/unread-count` - polling optimization

---

## Migration Patterns

### Pattern A: Convert to React Query Hook

**Before:**
```tsx
useEffect(() => {
  const load = async () => {
    const res = await fetchWithAuth('/api/v1/instructors/me');
    if (res.ok) {
      const data = await res.json();
      setProfile(data);
    }
  };
  load();
}, []);
```

**After:**
```tsx
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';

const { data: profile, isLoading } = useInstructorProfileMe();
```

### Pattern B: Accept Pre-fetched Data as Prop

**Before:**
```tsx
function ChildComponent() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetchWithAuth('/api/v1/instructors/me').then(r => r.json()).then(setData);
  }, []);
  // ...
}
```

**After:**
```tsx
interface Props {
  instructorProfile?: InstructorProfile | null;
}

function ChildComponent({ instructorProfile }: Props) {
  // Use instructorProfile directly, or fetch only if not provided
  const [data, setData] = useState(instructorProfile);

  useEffect(() => {
    if (instructorProfile) {
      setData(instructorProfile);
      return;
    }
    // Fallback fetch only if prop not provided
    fetchWithAuth('/api/v1/instructors/me').then(r => r.json()).then(setData);
  }, [instructorProfile]);
}
```

### Pattern C: Skip Hook When Data Available

```tsx
// Parent already fetches, skip in child
const isOnboardingPage = pathname?.startsWith('/instructor/onboarding');
const { data } = useInstructorProfileMe(!isOnboardingPage); // Skip if onboarding
```

---

## Testing Checklist

After each migration:

1. **Clear cache**: `rm -rf .next && npm run dev`
2. **Hard refresh**: Cmd+Shift+R / Ctrl+Shift+R
3. **Check console for**:
   - No 429 errors
   - Single API call per endpoint (not duplicates)
   - "from cache" log messages where applicable
4. **Run tests**: `npm run test`
5. **Run typecheck**: `npm run typecheck`

---

## Files Modified (Completed)

| Date | File | Change |
|------|------|--------|
| 2025-11-27 | `features/instructor-profile/InstructorProfileForm.tsx` | Use `useInstructorProfileMe` hook |
| 2025-11-27 | `features/instructor-profile/SkillsPricingInline.tsx` | Accept `instructorProfile` prop, conditional fetch |

---

## Next Steps

1. **ProgressSteps.tsx** - Convert to use `useInstructorProfileMe` or accept prop
2. **EditProfileModal.tsx** - Pass profile data when opening modal
3. **Create hooks for**: `/api/v1/auth/me`, `/api/v1/addresses/me` if not exists
4. **Audit other endpoints** for similar patterns

---

## Commands for Auditing

```bash
# Find all fetchWithAuth calls for a specific endpoint
grep -rn "fetchWithAuth.*instructors/me" frontend/ --include="*.tsx" --include="*.ts"

# Find components using a specific hook
grep -rn "useInstructorProfileMe" frontend/ --include="*.tsx" --include="*.ts"

# Find all useEffect + fetch patterns (potential duplicates)
grep -rn "useEffect" frontend/ --include="*.tsx" -A 5 | grep -B 2 "fetchWithAuth"
```

---

## Reference: Available React Query Hooks

### Instructor Hooks
| Hook | Endpoint | Location |
|------|----------|----------|
| `useInstructorProfileMe` | `/api/v1/instructors/me` | `@/hooks/queries/useInstructorProfileMe` |
| `useInstructorProfile` | `/api/v1/instructors/:id` | `@/features/instructor-profile/hooks/useInstructorProfile` |
| `useInstructorServices` | Instructor services | `@/features/instructor-profile/hooks/useInstructorServices` |
| `useInstructorAvailability` | Availability slots | `@/features/instructor-profile/hooks/useInstructorAvailability` |
| `useInstructorReviews` | Reviews | `@/features/instructor-profile/hooks/useInstructorReviews` |
| `useInstructorBookings` | Bookings | `@/hooks/queries/useInstructorBookings` |
| `useInstructorEarnings` | Earnings | `@/hooks/queries/useInstructorEarnings` |
| `useInstructorServiceAreas` | Service areas | `@/hooks/queries/useInstructorServiceAreas` |

### User/Auth Hooks
| Hook | Endpoint | Location |
|------|----------|----------|
| `useAuth` | `/api/v1/auth/me` | `@/hooks/queries/useAuth` |
| `useUser` | User data | `@/hooks/queries/useUser` |

### Onboarding Hooks
| Hook | Endpoint | Location |
|------|----------|----------|
| `useOnboardingStepStatus` | Multiple (unified) | `@/features/instructor-onboarding/useOnboardingStepStatus` |

### Other Hooks
| Hook | Endpoint | Location |
|------|----------|----------|
| `useServices` | Service catalog | `@/hooks/queries/useServices` |
| `useRatings` | Ratings | `@/hooks/queries/useRatings` |
| `useMyLessons` | Student lessons | `@/hooks/useMyLessons` |
| `useCredits` | Payment credits | `@/features/shared/payment/hooks/useCredits` |
| `useHomepage` | Homepage data | `@/hooks/queries/useHomepage` |

*Add new hooks to this list as they are created.*
