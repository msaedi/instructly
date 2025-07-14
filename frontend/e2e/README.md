# E2E Tests

End-to-end tests for InstaInstru using Playwright.

## Setup

1. Install Playwright browsers (one-time setup):
   ```bash
   npm run playwright:install
   ```

2. Make sure the dev server is running:
   ```bash
   npm run dev
   ```

## Running Tests

```bash
# Run CI-safe tests (recommended for CI/CD)
npm run test:e2e:ci

# Run working tests (includes search test that may fail without backend)
npm run test:e2e:working

# Run all tests (includes failing booking tests)
npm run test:e2e

# Run specific test file
npm run test:e2e -- e2e/tests/smoke.spec.ts

# Run tests with UI mode (recommended for development)
npm run test:e2e:ui

# Run tests in debug mode
npm run test:e2e:debug

# Run tests with browser visible
npm run test:e2e:headed

# View test report after running tests
npm run test:e2e:report
```

## Test Structure

- `tests/` - Test specifications
  - `smoke.spec.ts` - Basic smoke tests ✅ (PASSING)
  - `basic-search.spec.ts` - Basic search functionality ✅ (PASSING)
  - `booking-journey.spec.ts` - Full booking flow tests (requires backend)
  - `booking-journey-mocked.spec.ts` - Booking flow with API mocks
- `pages/` - Page Object Models
- `fixtures/` - Test data and API mocks

## Current Test Status

✅ **Passing Tests (CI-Safe):**
- Smoke tests (homepage, navigation)
- Example interaction flows
- Footer navigation

✅ **Passing Tests (Local):**
- All of the above plus:
- Basic search functionality (requires search page implementation)
- Category navigation

🚧 **In Progress:**
- Full booking journey (requires backend integration)
- Mocked booking flow

## Writing Tests

1. Use Page Object Model pattern for maintainability
2. Add data-testid attributes to elements for reliable selection
3. Mock API responses for faster, more reliable tests
4. Keep tests independent and atomic

## Troubleshooting

If tests fail:
1. Make sure the dev server is running (`npm run dev`)
2. Check the HTML report: `npm run test:e2e:report`
3. Run in headed mode to see what's happening: `npm run test:e2e:headed`
4. Use UI mode for debugging: `npm run test:e2e:ui`

## CI Configuration

Tests are configured to run in CI with:
- Parallel execution disabled
- 2 retries on failure
- Screenshots/videos on failure
- Currently only running Chromium (other browsers commented out)
