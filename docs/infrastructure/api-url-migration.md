# NEXT_PUBLIC_API_URL → NEXT_PUBLIC_API_BASE Migration

## Summary
Successfully migrated from `NEXT_PUBLIC_API_URL` to `NEXT_PUBLIC_API_BASE` to eliminate configuration ambiguity and establish a single source of truth for API configuration.

## What Changed

### Core Changes
1. **Single Source of Truth**: `lib/apiBase.ts` now manages all API base URL logic
2. **Fail-Fast Configuration**: Missing `NEXT_PUBLIC_API_BASE` causes immediate error
3. **Deprecation Guard**: Development builds fail if old `NEXT_PUBLIC_API_URL` is detected
4. **Proxy Mode Support**: Clean separation between proxy and direct API modes

### Files Updated
- **Configuration**: All `.env*` files now use `NEXT_PUBLIC_API_BASE`
- **Source Code**: 17 files updated to use new environment variable
- **Package Scripts**: npm scripts updated (`dev:http`, `dev:https`)
- **Tests**: Added comprehensive test coverage for migration

## Vercel Configuration Required

### ⚠️ ACTION REQUIRED: Update Vercel Environment Variables

You need to update the environment variables in Vercel for both preview and production:

1. **Preview Environment** (preview.instainstru.com):
   - Remove: `NEXT_PUBLIC_API_URL`
   - Add: `NEXT_PUBLIC_API_BASE=https://preview-api.instainstru.com`
   - Keep: `NEXT_PUBLIC_USE_PROXY=false`

2. **Production Environment** (www.instainstru.com):
   - Remove: `NEXT_PUBLIC_API_URL`
   - Add: `NEXT_PUBLIC_API_BASE=https://api.instainstru.com`
   - Ensure: `NEXT_PUBLIC_USE_PROXY=false`

### Steps to Update in Vercel:
1. Go to Vercel Dashboard → Project Settings → Environment Variables
2. Delete `NEXT_PUBLIC_API_URL` for all environments
3. Add `NEXT_PUBLIC_API_BASE` with appropriate values
4. Trigger a redeploy for changes to take effect

## Testing

### Run Migration Check
```bash
./scripts/check-api-url-migration.sh
```

### Run Tests
```bash
npm test -- __tests__/apiBase.test.ts
```

## Benefits

1. **No Ambiguity**: Single variable name across entire codebase
2. **Fail-Fast**: Misconfigurations caught immediately
3. **Better Developer Experience**: Clear error messages
4. **CI Protection**: Automated checks prevent regression
5. **Clean Proxy Mode**: Proxy configuration is now explicit and clean

## Technical Details

### API Base Resolution Logic
```typescript
// In lib/apiBase.ts
if (USE_PROXY) return '/api/proxy';  // Local dev with proxy
if (!rawBase) throw Error();         // Fail if not configured
return rawBase;                      // Use configured base
```

### Guard Against Old Variable
```typescript
if (process.env.NEXT_PUBLIC_API_URL) {
  if (process.env.NODE_ENV !== 'production') {
    throw new Error('NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
  }
  logger.error('WARNING: NEXT_PUBLIC_API_URL is deprecated. Use NEXT_PUBLIC_API_BASE.');
}
```

## Migration Complete ✅

All phases of the surgical migration plan have been successfully completed:
- Phase A: apiBase.ts is single source of truth ✅
- Phase B: All code uses NEXT_PUBLIC_API_BASE ✅
- Phase C: Tests and CI guards in place ✅
- Phase D: Environment files updated ✅
- Phase E: Documentation complete ✅

The only remaining step is updating the Vercel environment variables as described above.
