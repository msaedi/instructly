/**
 * useMessageDrafts - Hook for managing message draft persistence
 *
 * Handles:
 * - Loading drafts from cookies on mount
 * - Persisting drafts to cookies on change
 * - Draft management per thread
 */

import { useState, useEffect, useCallback } from 'react';
import { COMPOSE_THREAD_ID } from '../constants';
import { readDraftCookie, writeDraftCookie } from './useMessageDrafts.helpers';

/**
 * Load drafts from cookie storage
 */
const loadInitialDrafts = (): Record<string, string> => {
  return readDraftCookie(typeof document === 'undefined' ? undefined : document);
};

export type UseMessageDraftsResult = {
  draftsByThread: Record<string, string>;
  setDraftsByThread: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  getDraftKey: (threadId: string | null) => string;
  getCurrentDraft: (threadId: string | null) => string;
  updateDraft: (threadId: string | null, value: string) => void;
  clearDraft: (threadId: string | null) => void;
};

export function useMessageDrafts(): UseMessageDraftsResult {
  const [draftsByThread, setDraftsByThread] = useState<Record<string, string>>(loadInitialDrafts);

  // Persist drafts to cookie on change
  useEffect(() => {
    writeDraftCookie(draftsByThread, typeof document === 'undefined' ? undefined : document);
  }, [draftsByThread]);

  const getDraftKey = useCallback((threadId: string | null): string => {
    return threadId ?? COMPOSE_THREAD_ID;
  }, []);

  const getCurrentDraft = useCallback(
    (threadId: string | null): string => {
      const key = getDraftKey(threadId);
      return draftsByThread[key] ?? '';
    },
    [draftsByThread, getDraftKey]
  );

  const updateDraft = useCallback(
    (threadId: string | null, value: string) => {
      const key = getDraftKey(threadId);
      setDraftsByThread((prev) => {
        if (prev[key] === value) return prev;
        return { ...prev, [key]: value };
      });
    },
    [getDraftKey]
  );

  const clearDraft = useCallback(
    (threadId: string | null) => {
      const key = getDraftKey(threadId);
      setDraftsByThread((prev) => {
        if (!prev[key]) return prev;
        return { ...prev, [key]: '' };
      });
    },
    [getDraftKey]
  );

  return {
    draftsByThread,
    setDraftsByThread,
    getDraftKey,
    getCurrentDraft,
    updateDraft,
    clearDraft,
  };
}
