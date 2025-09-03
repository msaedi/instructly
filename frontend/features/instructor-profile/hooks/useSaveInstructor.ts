import { useMutation, useQueryClient } from '@tanstack/react-query';
import { mutationFn } from '@/lib/react-query/api';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { useState, useEffect } from 'react';

interface SavedInstructor {
  instructor_id: string;
  saved_at: string;
}

/**
 * Hook to manage saved/favorite instructors with optimistic updates
 * Handles both logged-in (persisted) and logged-out (localStorage) states
 */
export function useSaveInstructor(instructorId: string) {
  const queryClient = useQueryClient();
  const { isAuthenticated } = useAuth();
  const [isSaved, setIsSaved] = useState(false);

  // Check if instructor is saved (sessionStorage for non-authenticated users)
  useEffect(() => {
    if (!isAuthenticated) {
      const savedInstructors = sessionStorage.getItem('savedInstructors');
      if (savedInstructors) {
        const saved = JSON.parse(savedInstructors) as string[];
        setIsSaved(saved.includes(instructorId));
      }
    }
  }, [instructorId, isAuthenticated]);

  // Mutation for saving instructor (authenticated users)
  const saveMutation = useMutation<SavedInstructor, Error, void>({
    mutationFn: async () => {
      const result = await mutationFn('/users/saved-instructors', {
        method: 'POST',
        requireAuth: true,
      })({ instructor_id: instructorId });
      return result as unknown as SavedInstructor;
    },

    onMutate: async () => {
      // Optimistically update UI
      setIsSaved(true);
    },

    onError: () => {
      // Revert on error
      setIsSaved(false);
    },

    onSuccess: () => {
      // Invalidate saved instructors query
      queryClient.invalidateQueries({ queryKey: ['users', 'saved-instructors'] });
    },
  });

  // Mutation for removing saved instructor (authenticated users)
  const unsaveMutation = useMutation<void, Error, void>({
    mutationFn: async () => {
      const fn = mutationFn(`/users/saved-instructors/${instructorId}`, {
        method: 'DELETE',
        requireAuth: true,
      });
      await fn({});
      return;
    },

    onMutate: async () => {
      // Optimistically update UI
      setIsSaved(false);
    },

    onError: () => {
      // Revert on error
      setIsSaved(true);
    },

    onSuccess: () => {
      // Invalidate saved instructors query
      queryClient.invalidateQueries({ queryKey: ['users', 'saved-instructors'] });
    },
  });

  // Toggle save state
  const toggleSave = () => {
    if (!isAuthenticated) {
      // Handle sessionStorage for non-authenticated users
      const savedInstructors = sessionStorage.getItem('savedInstructors');
      let saved: string[] = savedInstructors ? JSON.parse(savedInstructors) : [];

      if (isSaved) {
        saved = saved.filter(id => id !== instructorId);
      } else {
        saved.push(instructorId);
      }

      sessionStorage.setItem('savedInstructors', JSON.stringify(saved));
      setIsSaved(!isSaved);

      // Optionally show a toast to prompt login
      // toast.info('Sign in to save instructors across devices');
    } else {
      // Handle API calls for authenticated users
      if (isSaved) {
        unsaveMutation.mutate();
      } else {
        saveMutation.mutate();
      }
    }
  };

  return {
    isSaved,
    toggleSave,
    isLoading: saveMutation.isPending || unsaveMutation.isPending,
  };
}
