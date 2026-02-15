import { renderHook, waitFor, act } from '@testing-library/react';
import { useRouter } from 'next/navigation';
import {
  useAuth,
  storeBookingIntent,
  getBookingIntent,
  clearBookingIntent,
} from '../useAuth';
import { httpGet, ApiError } from '@/lib/http';

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

// Mock http module
jest.mock('@/lib/http', () => ({
  httpGet: jest.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    data?: Record<string, unknown>;
    constructor(message: string, status: number, data?: Record<string, unknown>) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.data = data;
    }
  },
}));

// Mock apiBase
jest.mock('@/lib/apiBase', () => ({
  withApiBase: jest.fn((url: string) => `https://api.test.com${url}`),
}));

// Mock API endpoints
jest.mock('@/lib/api', () => ({
  API_ENDPOINTS: {
    ME: '/api/v1/users/me',
  },
}));

// Mock logger
jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

const useRouterMock = useRouter as jest.Mock;
const httpGetMock = httpGet as jest.Mock;

describe('useAuth hook', () => {
  const mockReplace = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({
      replace: mockReplace,
      push: jest.fn(),
      prefetch: jest.fn(),
    });
    // Clear sessionStorage
    sessionStorage.clear();
  });

  describe('initial state', () => {
    it('starts with loading state', () => {
      httpGetMock.mockImplementation(() => new Promise(() => {})); // Never resolves

      const { result } = renderHook(() => useAuth());

      expect(result.current.isLoading).toBe(true);
      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.error).toBeNull();
    });
  });

  describe('authenticated state', () => {
    const mockUser = {
      id: 'user-123',
      email: 'test@example.com',
      full_name: 'Test User',
      roles: ['student'],
      permissions: ['read:bookings'],
      is_active: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };

    it('sets user and authenticated state on success', async () => {
      httpGetMock.mockResolvedValueOnce(mockUser);

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.user).toEqual(mockUser);
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.error).toBeNull();
    });

    it('exposes checkAuth function that can be called manually', async () => {
      httpGetMock.mockResolvedValueOnce(mockUser);

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Reset mock and call checkAuth manually
      httpGetMock.mockResolvedValueOnce({ ...mockUser, email: 'updated@example.com' });

      await act(async () => {
        await result.current.checkAuth();
      });

      expect(result.current.user?.email).toBe('updated@example.com');
    });
  });

  describe('unauthenticated state (401)', () => {
    it('sets user to null on 401 error', async () => {
      const error = new ApiError('Unauthorized', 401);
      httpGetMock.mockRejectedValueOnce(error);

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.error).toBeNull(); // 401 is not an error state
    });
  });

  describe('network error state', () => {
    it('sets error message on network failure', async () => {
      const networkError = new Error('Network error');
      httpGetMock.mockRejectedValueOnce(networkError);

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.error).toBe('Network error while checking authentication');
    });

    it('sets error message on non-401 API errors', async () => {
      const serverError = new ApiError('Server Error', 500);
      httpGetMock.mockRejectedValueOnce(serverError);

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.error).toBe('Network error while checking authentication');
    });
  });

  describe('redirectToLogin', () => {
    it('redirects to login with current path as return URL', async () => {
      httpGetMock.mockResolvedValueOnce(null);
      window.history.pushState({}, '', '/booking?instructor=123');

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      act(() => {
        result.current.redirectToLogin();
      });

      expect(mockReplace).toHaveBeenCalledWith(
        '/login?redirect=%2Fbooking%3Finstructor%3D123'
      );
    });

    it('accepts custom return URL', async () => {
      httpGetMock.mockResolvedValueOnce(null);

      const { result } = renderHook(() => useAuth());

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      act(() => {
        result.current.redirectToLogin('/custom/path');
      });

      expect(mockReplace).toHaveBeenCalledWith('/login?redirect=%2Fcustom%2Fpath');
    });
  });
});

describe('storeBookingIntent', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('stores booking intent in sessionStorage', () => {
    const intent = {
      instructorId: 'inst-123',
      serviceId: 'svc-456',
      date: '2024-12-25',
      time: '14:00',
      duration: 60,
    };

    storeBookingIntent(intent);

    const stored = sessionStorage.getItem('bookingIntent');
    expect(stored).toBe(JSON.stringify(intent));
  });

  it('stores booking intent with optional skipModal flag', () => {
    const intent = {
      instructorId: 'inst-123',
      date: '2024-12-25',
      time: '14:00',
      duration: 60,
      skipModal: true,
    };

    storeBookingIntent(intent);

    const stored = JSON.parse(sessionStorage.getItem('bookingIntent') ?? '{}');
    expect(stored.skipModal).toBe(true);
  });

  it('handles storage error gracefully', () => {
    // Mock sessionStorage.setItem to throw
    const originalSetItem = sessionStorage.setItem;
    sessionStorage.setItem = jest.fn(() => {
      throw new Error('Storage full');
    });

    // Should not throw
    expect(() => {
      storeBookingIntent({
        instructorId: 'inst-123',
        date: '2024-12-25',
        time: '14:00',
        duration: 60,
      });
    }).not.toThrow();

    sessionStorage.setItem = originalSetItem;
  });
});

describe('getBookingIntent', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('retrieves stored booking intent', () => {
    const intent = {
      instructorId: 'inst-123',
      serviceId: 'svc-456',
      date: '2024-12-25',
      time: '14:00',
      duration: 60,
    };

    sessionStorage.setItem('bookingIntent', JSON.stringify(intent));

    const retrieved = getBookingIntent();
    expect(retrieved).toEqual(intent);
  });

  it('returns null when no intent stored', () => {
    const retrieved = getBookingIntent();
    expect(retrieved).toBeNull();
  });

  it('returns null on invalid JSON', () => {
    sessionStorage.setItem('bookingIntent', 'invalid-json');

    const retrieved = getBookingIntent();
    expect(retrieved).toBeNull();
  });

  it('handles storage error gracefully', () => {
    // Mock sessionStorage.getItem to throw
    const originalGetItem = sessionStorage.getItem;
    sessionStorage.getItem = jest.fn(() => {
      throw new Error('Storage access denied');
    });

    const retrieved = getBookingIntent();
    expect(retrieved).toBeNull();

    sessionStorage.getItem = originalGetItem;
  });
});

describe('clearBookingIntent', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('removes booking intent from sessionStorage', () => {
    sessionStorage.setItem('bookingIntent', JSON.stringify({ instructorId: 'inst-123' }));

    clearBookingIntent();

    expect(sessionStorage.getItem('bookingIntent')).toBeNull();
  });

  it('does not throw when no intent exists', () => {
    expect(() => clearBookingIntent()).not.toThrow();
  });

  it('handles storage error gracefully', () => {
    // Mock sessionStorage.removeItem to throw
    const originalRemoveItem = sessionStorage.removeItem;
    sessionStorage.removeItem = jest.fn(() => {
      throw new Error('Storage access denied');
    });

    expect(() => clearBookingIntent()).not.toThrow();

    sessionStorage.removeItem = originalRemoveItem;
  });
});
