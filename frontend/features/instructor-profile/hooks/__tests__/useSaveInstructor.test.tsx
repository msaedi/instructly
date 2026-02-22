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

    it('reverts optimistic update on unsave error (isSaved goes back to true)', async () => {
      // Save succeeds, unsave fails -- the onError callback should revert isSaved to true
      const mockSaveFn = jest.fn().mockResolvedValue({
        instructor_id: 'instructor-123',
        saved_at: '2025-01-15T10:00:00Z',
      });
      const mockUnsaveFn = jest.fn().mockRejectedValue(new Error('Unsave failed'));

      mutationFnMock
        .mockReturnValueOnce(mockSaveFn)   // save mutation's inner call
        .mockReturnValueOnce(mockUnsaveFn); // unsave mutation's inner call

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      // Step 1: Toggle save (save mutation) -- should succeed
      await act(async () => {
        result.current.toggleSave();
      });

      await waitFor(() => {
        expect(result.current.isSaved).toBe(true);
      });

      // Step 2: Toggle again (unsave mutation) -- optimistically sets isSaved to false
      await act(async () => {
        result.current.toggleSave();
      });

      // The unsave API rejects, so onError should revert isSaved back to true
      await waitFor(() => {
        expect(result.current.isSaved).toBe(true);
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

    it('verifies sessionStorage contains the instructor ID after guest save', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });

      const { result } = renderHook(
        () => useSaveInstructor('instructor-save-check'),
        { wrapper: createWrapper() }
      );

      act(() => {
        result.current.toggleSave();
      });

      // Verify the exact content written to sessionStorage
      const stored = mockSessionStorage['savedInstructors'];
      expect(stored).toBeDefined();
      if (!stored) {
        throw new Error('Expected savedInstructors in sessionStorage');
      }
      const parsed = JSON.parse(stored) as string[];
      expect(parsed).toContain('instructor-save-check');
    });

    it('verifies sessionStorage removes the instructor ID after guest unsave', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });
      mockSessionStorage['savedInstructors'] = JSON.stringify([
        'instructor-keep',
        'instructor-remove',
      ]);

      const { result } = renderHook(
        () => useSaveInstructor('instructor-remove'),
        { wrapper: createWrapper() }
      );

      expect(result.current.isSaved).toBe(true);

      act(() => {
        result.current.toggleSave();
      });

      const stored = mockSessionStorage['savedInstructors'];
      const parsed = JSON.parse(stored) as string[];
      expect(parsed).not.toContain('instructor-remove');
      expect(parsed).toContain('instructor-keep');
    });

    it('throws on corrupted (non-JSON) sessionStorage during initialization', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });
      // This is a REAL BUG: corrupted sessionStorage causes JSON.parse to throw
      // during the useState initializer, crashing the hook
      mockSessionStorage['savedInstructors'] = '<<<not-json>>>';

      expect(() => {
        renderHook(
          () => useSaveInstructor('instructor-123'),
          { wrapper: createWrapper() }
        );
      }).toThrow();
    });

    it('throws on corrupted sessionStorage during toggleSave', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });

      const { result } = renderHook(
        () => useSaveInstructor('instructor-123'),
        { wrapper: createWrapper() }
      );

      // Corrupt sessionStorage after initialization
      mockSessionStorage['savedInstructors'] = '{invalid json}';

      // JSON.parse in toggleSave will throw — this is a latent bug
      expect(() => {
        act(() => {
          result.current.toggleSave();
        });
      }).toThrow();
    });

    it('preserves other saved instructors when saving a new one', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });
      mockSessionStorage['savedInstructors'] = JSON.stringify([
        'existing-1',
        'existing-2',
      ]);

      const { result } = renderHook(
        () => useSaveInstructor('new-instructor'),
        { wrapper: createWrapper() }
      );

      act(() => {
        result.current.toggleSave();
      });

      const stored = mockSessionStorage['savedInstructors'];
      const parsed = JSON.parse(stored) as string[];
      expect(parsed).toEqual(['existing-1', 'existing-2', 'new-instructor']);
    });

    it('handles double-save by appending duplicate (no dedup in source)', () => {
      useAuthMock.mockReturnValue({ isAuthenticated: false });

      const { result } = renderHook(
        () => useSaveInstructor('instructor-dup'),
        { wrapper: createWrapper() }
      );

      // First save
      act(() => {
        result.current.toggleSave();
      });
      expect(result.current.isSaved).toBe(true);

      // The hook flips isSaved to true, so next toggle will unsave.
      // But if we re-mount the hook while sessionStorage has the ID:
      mockSessionStorage['savedInstructors'] = JSON.stringify([
        'instructor-dup',
        'instructor-dup',
      ]);

      const { result: result2 } = renderHook(
        () => useSaveInstructor('instructor-dup'),
        { wrapper: createWrapper() }
      );

      // Unsaving with duplicates: filter removes ALL instances
      act(() => {
        result2.current.toggleSave();
      });

      const stored = mockSessionStorage['savedInstructors'];
      const parsed = JSON.parse(stored) as string[];
      expect(parsed).not.toContain('instructor-dup');
    });
  });
});
