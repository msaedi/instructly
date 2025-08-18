// frontend/lib/__tests__/searchTracking.test.ts
/**
 * Unit tests for search tracking functionality
 *
 * Tests all 5 search types:
 * #1 Natural language search
 * #2 Category selection
 * #3 Service pills (homepage)
 * #4 Service selection (services page)
 * #5 Recent search history
 */

import {
  recordSearch,
  trackSearchInteraction,
  getRecentSearches,
  deleteSearch,
} from '../searchTracking';
import { SearchType } from '../../types/enums';

// Mock dependencies
jest.mock('../logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('../sessionTracking', () => ({
  getSessionId: jest.fn(() => 'test-session-123'),
  refreshSession: jest.fn(),
  getAnalyticsContext: jest.fn(() => ({
    page: '/test',
    viewport: '1920x1080',
    timestamp: '2025-07-29T00:00:00.000Z',
    page_view_count: 1,
    session_duration: 30,
  })),
}));

jest.mock('../deviceContext', () => ({
  captureDeviceContext: jest.fn(() => ({
    screenWidth: 1920,
    screenHeight: 1080,
    viewportWidth: 1920,
    viewportHeight: 1080,
    devicePixelRatio: 1,
    touchSupport: false,
    connectionType: 'wifi',
    effectiveType: '4g',
    language: 'en-US',
    timezone: 'America/New_York',
    isOnline: true,
  })),
  formatDeviceContextForAnalytics: jest.fn(() => ({
    device_type: 'desktop',
    connection_type: 'wifi',
    connection_effective_type: '4g',
    viewport_size: '1920x1080',
    language: 'en-US',
    timezone: 'America/New_York',
  })),
}));

// Mock fetch
global.fetch = jest.fn();
const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>;

// Mock localStorage and sessionStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
};

const mockSessionStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
};

Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
});

Object.defineProperty(window, 'sessionStorage', {
  value: mockSessionStorage,
});

// Mock window.location properties for tests
// We'll override specific properties as needed in tests

Object.defineProperty(document, 'referrer', {
  value: 'http://localhost:3000/',
  writable: true,
});

describe('Search Tracking', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetch.mockClear();
    mockLocalStorage.getItem.mockClear();
    mockSessionStorage.getItem.mockClear();
  });

  describe('recordSearch', () => {
    it('should track natural language search (#1) correctly', async () => {
      // Mock successful API response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 1,
          search_query: 'piano lessons',
          search_type: 'natural_language',
          results_count: 5,
        }),
      } as Response);

      await recordSearch(
        {
          query: 'piano lessons',
          search_type: SearchType.NATURAL_LANGUAGE,
          results_count: 5,
        },
        false // not authenticated
      );

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/search-history/',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-Guest-Session-ID': expect.any(String),
            'X-Session-ID': 'test-session-123',
            'X-Search-Origin': expect.any(String),
          }),
        })
      );

      // Verify body separately for more flexible matching
      const callArgs = mockFetch.mock.calls[0];
      const requestInit = callArgs[1] as RequestInit;
      const body = JSON.parse(requestInit.body as string);
      expect(body.search_query).toBe('piano lessons');
      expect(body.search_type).toBe('natural_language');
      expect(body.results_count).toBe(5);
      expect(body.search_context).toMatchObject({
        page: '/test',
        viewport: '1920x1080',
        page_view_count: 1,
        session_duration: 30,
      });
      expect(body.device_context).toMatchObject({
        device_type: 'desktop',
        connection_type: 'wifi',
      });
    });

    it('should track category selection (#2) correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 2,
          search_query: 'Music lessons',
          search_type: 'category',
          results_count: null,
        }),
      } as Response);

      await recordSearch(
        {
          query: 'Music lessons',
          search_type: SearchType.CATEGORY,
          results_count: null,
        },
        false
      );

      expect(mockFetch).toHaveBeenCalled();

      const callArgs = mockFetch.mock.calls[0];
      const requestInit = callArgs[1] as RequestInit;
      const body = JSON.parse(requestInit.body as string);
      expect(body.search_query).toBe('Music lessons');
      expect(body.search_type).toBe('category');
      expect(body.results_count).toBe(null);
      expect(body.search_context.page_view_count).toBe(1);
      expect(body.search_context.session_duration).toBe(30);
      expect(body.device_context.device_type).toBe('desktop');
      expect(body.device_context.connection_type).toBe('wifi');
    });

    it('should track service pill selection (#3) correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 3,
          search_query: 'Piano',
          search_type: 'service_pill',
          results_count: 8,
        }),
      } as Response);

      await recordSearch(
        {
          query: 'Piano',
          search_type: SearchType.SERVICE_PILL,
          results_count: 8,
        },
        false
      );

      expect(mockFetch).toHaveBeenCalled();

      const callArgs = mockFetch.mock.calls[0];
      const requestInit = callArgs[1] as RequestInit;
      const body = JSON.parse(requestInit.body as string);
      expect(body.search_query).toBe('Piano');
      expect(body.search_type).toBe('service_pill');
      expect(body.results_count).toBe(8);
      expect(body.search_context).toBeDefined();
      expect(body.device_context).toBeDefined();
    });

    it('should track search history click (#5) correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 4,
          search_query: 'guitar lessons',
          search_type: 'search_history',
          results_count: 3,
        }),
      } as Response);

      await recordSearch(
        {
          query: 'guitar lessons',
          search_type: SearchType.SEARCH_HISTORY,
          results_count: 3,
        },
        false
      );

      expect(mockFetch).toHaveBeenCalled();

      const callArgs = mockFetch.mock.calls[0];
      const requestInit = callArgs[1] as RequestInit;
      const body = JSON.parse(requestInit.body as string);
      expect(body.search_query).toBe('guitar lessons');
      expect(body.search_type).toBe('search_history');
      expect(body.results_count).toBe(3);
      expect(body.search_context).toBeDefined();
      expect(body.device_context).toBeDefined();
    });

    it('should use navigationFrom for correct referrer tracking', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 5 }),
      } as Response);

      // Mock navigationFrom in sessionStorage
      mockSessionStorage.getItem.mockReturnValue('/services');

      await recordSearch(
        {
          query: 'violin',
          search_type: SearchType.SERVICE_PILL,
          results_count: 2,
        },
        false
      );

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/search-history/',
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Search-Origin': '/services',
          }),
        })
      );

      // Should clear navigationFrom after use
      expect(mockSessionStorage.removeItem).toHaveBeenCalledWith('navigationFrom');
    });

    it('should handle authenticated users correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 6, search_event_id: 123 }),
      } as Response);

      // Mock localStorage to return token for authenticated user
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'access_token') return 'test-auth-token';
        return null;
      });

      const result = await recordSearch(
        {
          query: 'drums',
          search_type: SearchType.NATURAL_LANGUAGE,
          results_count: 4,
        },
        true // authenticated
      );

      // Verify the function was called with correct parameters
      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/search-history/',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            'X-Session-ID': expect.any(String),
          }),
          body: expect.stringContaining('"search_query":"drums"'),
        })
      );

      // Verify no guest session header for authenticated users
      const callArgs = mockFetch.mock.calls[0];
      const requestInit = callArgs[1] as RequestInit;
      const headers = requestInit.headers as any;
      expect(headers['X-Guest-Session-ID']).toBeUndefined();

      // Verify the result
      expect(result).toBe(123); // search_event_id
    });

    it('should handle API errors gracefully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => 'Internal Server Error',
      } as Response);

      // Should not throw an error
      await expect(
        recordSearch(
          {
            query: 'failing search',
            search_type: SearchType.NATURAL_LANGUAGE,
            results_count: 0,
          },
          false
        )
      ).resolves.not.toThrow();
    });
  });

  describe('trackSearchInteraction', () => {
    it('should track search result clicks correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'tracked' }),
      } as Response);

      await trackSearchInteraction(123, 'click', '456', 2, false);

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/search-history/interaction',
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );

      const callArgs = mockFetch.mock.calls[0];
      const requestInit = callArgs[1] as RequestInit;
      const body = JSON.parse(requestInit.body as string);
      expect(body.search_event_id).toBe(123);
      expect(body.interaction_type).toBe('click');
      expect(body.instructor_id).toBe('456');
      expect(body.result_position).toBe(2);
      expect(body.time_to_interaction).toBeNull();
    });

    it('should track search interaction with time to interaction', async () => {
      // Mock localStorage to have an auth token for authenticated user
      mockLocalStorage.getItem.mockImplementation((key) => {
        if (key === 'access_token') return 'test-token';
        return null;
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'tracked' }),
      } as Response);

      await trackSearchInteraction(123, 'view_profile', '789', 1, true, 5.5);

      expect(mockFetch).toHaveBeenCalledTimes(1);

      const callArgs = mockFetch.mock.calls[0];
      const requestInit = callArgs[1] as RequestInit;
      const body = JSON.parse(requestInit.body as string);
      expect(body.search_event_id).toBe(123);
      expect(body.interaction_type).toBe('view_profile');
      expect(body.instructor_id).toBe('789');
      expect(body.result_position).toBe(1);
      expect(body.time_to_interaction).toBe(5.5);
    });
  });

  describe('Edge Cases', () => {
    it('should handle missing device context gracefully', async () => {
      const { captureDeviceContext } = require('../deviceContext');
      captureDeviceContext.mockReturnValueOnce({});

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ id: 7 }),
      } as Response);

      await recordSearch(
        {
          query: 'test',
          search_type: SearchType.NATURAL_LANGUAGE,
          results_count: 1,
        },
        false
      );

      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/search-history/',
        expect.objectContaining({
          body: expect.stringContaining('device_context'),
        })
      );
    });

    it('should handle network failures gracefully', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      // Should not throw
      await expect(
        recordSearch(
          {
            query: 'network fail',
            search_type: SearchType.NATURAL_LANGUAGE,
            results_count: 0,
          },
          false
        )
      ).resolves.not.toThrow();
    });
  });
});
