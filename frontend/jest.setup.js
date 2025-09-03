import '@testing-library/jest-dom';

// Ensure proxy mode is disabled in tests for consistent URL expectations
process.env.NEXT_PUBLIC_USE_PROXY = 'false';
process.env.NEXT_PUBLIC_API_BASE = 'http://localhost:8000';

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  })),
  usePathname: jest.fn(() => '/'),
  useSearchParams: jest.fn(() => new URLSearchParams()),
}));

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

// Reset all mocks before each test
beforeEach(() => {
  jest.clearAllMocks();
});

// Provide a minimal global.fetch mock for tests (jsdom doesn't include fetch by default)
if (typeof global.fetch === 'undefined') {
  global.fetch = jest.fn(async (input, _init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    // Stub ratings endpoint
    if (/\/api\/reviews\/instructor\/.+\/ratings$/.test(url)) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          overall: { rating: 4.6, total_reviews: 5, display_rating: '4.6★' },
          by_service: [],
          confidence_level: 'established',
        }),
      };
    }
    // Stub booking review endpoint
    if (/\/api\/reviews\/booking\/.+/.test(url)) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    // Default empty JSON response
    return { ok: true, status: 200, json: async () => ({}) };
  });
}

// Silence React act() warnings in tests after we batch state updates at component level.
// These warnings are emitted via console.error and can cause CI noise/failures.
// We filter only the specific message while preserving all other errors.
let errorSpy;
const originalConsoleError = console.error;
beforeAll(() => {
  errorSpy = jest.spyOn(console, 'error').mockImplementation((...args) => {
    const [firstArg] = args;
    if (typeof firstArg === 'string' && firstArg.includes('not wrapped in act')) {
      return;
    }
    originalConsoleError(...args);
  });
});
afterAll(() => {
  if (errorSpy && typeof errorSpy.mockRestore === 'function') {
    errorSpy.mockRestore();
  }
});
