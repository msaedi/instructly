/**
 * useMessageDrafts - Hook for managing message draft persistence
 *
 * Handles:
 * - Loading drafts from cookies on mount
 * - Persisting drafts to cookies on change
 * - Draft management per thread
 */

import { useState, useEffect, useCallback } from 'react';
import { DRAFT_COOKIE_NAME, COMPOSE_THREAD_ID } from '../constants';

/**
 * Load drafts from cookie storage
 */
const loadInitialDrafts = (): Record<string, string> => {
  if (typeof document === 'undefined') return {};
  try {
    const cookies = document.cookie.split(';').map((cookie) => cookie.trim());
    const target = cookies.find((cookie) => cookie.startsWith(`${DRAFT_COOKIE_NAME}=`));
    if (!target) return {};
    const raw = decodeURIComponent(target.split('=')[1] ?? '');
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const entries = Object.entries(parsed).filter(([, value]) => typeof value === 'string') as [string, string][];
      return Object.fromEntries(entries);
    }
  } catch {
    // ignore malformed storage
  }
  return {};
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
    if (typeof document === 'undefined') return;
    try {
      const filtered = Object.entries(draftsByThread).filter(([, value]) => value !== '');
      if (filtered.length === 0) {
        document.cookie = `${DRAFT_COOKIE_NAME}=; path=/; max-age=0`;
        return;
      }
      const payload = encodeURIComponent(JSON.stringify(Object.fromEntries(filtered)));
      document.cookie = `${DRAFT_COOKIE_NAME}=${payload}; path=/; max-age=604800; SameSite=Lax`;
    } catch {
      // ignore storage errors
    }
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
