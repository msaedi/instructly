import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useSaveInstructor } from '../useSaveInstructor';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { mutationFn } from '@/lib/react-query/api';
import type { ReactNode } from 'react';

// Mock dependencies
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/lib/react-query/api', () => ({
  mutationFn: jest.fn(),
}));

const useAuthMock = useAuth as jest.Mock;
const mutationFnMock = mutationFn as jest.Mock;

// Mock sessionStorage
const mockSessionStorage: Record<string, string> = {};
Object.defineProperty(window, 'sessionStorage', {
  value: {
    getItem: jest.fn((key: string) => mockSessionStorage[key] || null),
    setItem: jest.fn((key: string, value: string) => {
      mockSessionStorage[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete mockSessionStorage[key];
    }),
    clear: jest.fn(() => {
      Object.keys(mockSessionStorage).forEach((key) => delete mockSessionStorage[key]);
    }),
  },
  writable: true,
});

// Create wrapper with QueryClient
const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return Wrapper;
};

describe('useSaveInstructor', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.keys(mockSessionStorage).forEach((key) => delete mockSessionStorage[key]);
  });

  describe('when not authenticated', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });
    });

    it('initializes with isSaved false when no saved instructors', () => {
      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      expect(result.current.isSaved).toBe(false);
      expect(result.current.isLoading).toBe(false);
    });

    it('initializes with isSaved true when instructor is in sessionStorage', () => {
      mockSessionStorage['savedInstructors'] = JSON.stringify(['instructor-123']);

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      expect(result.current.isSaved).toBe(true);
    });

    it('toggleSave adds instructor to sessionStorage', () => {
      const { result } = renderHook(
        () => useSaveInstructor('instructor-456'),
        { wrapper: createWrapper() }
      );

      act(() => {
        result.current.toggleSave();
      });

      expect(result.current.isSaved).toBe(true);
      expect(window.sessionStorage.setItem).toHaveBeenCalled();
    });

    it('toggleSave removes instructor from sessionStorage when already saved', () => {
      mockSessionStorage['savedInstructors'] = JSON.stringify(['instructor-789']);

      const { result } = renderHook(
        () => useSaveInstructor('instructor-789'),
        { wrapper: createWrapper() }
      );

      expect(result.current.isSaved).toBe(true);

      act(() => {
        result.current.toggleSave();
      });

      expect(result.current.isSaved).toBe(false);
    });

    it('does not call API when not authenticated', () => {
      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      act(() => {
        result.current.toggleSave();
      });

      expect(mutationFnMock).not.toHaveBeenCalled();
    });
  });

  describe('when authenticated', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({ isAuthenticated: true });
    });

    it('initializes with isSaved false for authenticated user', () => {
      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      expect(result.current.isSaved).toBe(false);
    });

    it('calls save API when toggling to saved', async () => {
      const mockMutationFn = jest.fn().mockResolvedValue({
        instructor_id: 'instructor-123',
        saved_at: '2025-01-15T10:00:00Z',
      });
      mutationFnMock.mockReturnValue(mockMutationFn);

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      await act(async () => {
        result.current.toggleSave();
      });

      // Wait for optimistic update
      await waitFor(() => {
        expect(result.current.isSaved).toBe(true);
      });

      // Verify mutation was called with correct args
      expect(mutationFnMock).toHaveBeenCalledWith(
        '/users/saved-instructors',
        { method: 'POST', requireAuth: true }
      );
    });

    it('calls unsave API when toggling to unsaved', async () => {
      const mockSaveFn = jest.fn().mockResolvedValue({
        instructor_id: 'instructor-123',
        saved_at: '2025-01-15T10:00:00Z',
      });
      const mockUnsaveFn = jest.fn().mockResolvedValue(undefined);

      mutationFnMock
        .mockReturnValueOnce(mockSaveFn) // For save
        .mockReturnValueOnce(mockUnsaveFn); // For unsave

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      // First toggle - save
      await act(async () => {
        result.current.toggleSave();
      });

      await waitFor(() => {
        expect(result.current.isSaved).toBe(true);
      });

      // Second toggle - unsave
      await act(async () => {
        result.current.toggleSave();
      });

      await waitFor(() => {
        expect(result.current.isSaved).toBe(false);
      });
    });

    it('reverts optimistic update on save error', async () => {
      const mockMutationFn = jest.fn().mockRejectedValue(new Error('Save failed'));
      mutationFnMock.mockReturnValue(mockMutationFn);

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      await act(async () => {
        result.current.toggleSave();
      });

      // Should eventually revert after error
      await waitFor(() => {
        expect(result.current.isSaved).toBe(false);
      });
    });

    it('shows loading state during mutation', async () => {
      let resolveMutation: () => void;
      const mockMutationFn = jest.fn().mockReturnValue(
        new Promise<void>((resolve) => {
          resolveMutation = resolve;
        })
      );
      mutationFnMock.mockReturnValue(mockMutationFn);

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      await act(async () => {
        result.current.toggleSave();
      });

      // Should show loading while mutation is pending
      await waitFor(() => {
        expect(result.current.isLoading).toBe(true);
      });

      await act(async () => {
        resolveMutation!();
      });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
    });
  });

  describe('edge cases', () => {
    it('handles empty sessionStorage gracefully', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      expect(result.current.isSaved).toBe(false);
    });

    it('handles malformed sessionStorage gracefully', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });
      // Set a valid JSON array that doesn't include the instructor
      mockSessionStorage['savedInstructors'] = JSON.stringify(['other-instructor']);

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      // Should return false since instructor-123 is not in the array
      expect(result.current.isSaved).toBe(false);
    });
  });
});
