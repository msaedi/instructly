// frontend/components/chat/ChatModal.tsx
'use client';

/**
 * Chat modal/drawer component that adapts to screen size.
 *
 * - Mobile: Full-screen drawer from bottom
 * - Desktop: Modal dialog
 *
 * Handles proper focus management and accessibility.
 */

import { useCallback, useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Chat } from './Chat';
import { QueryErrorBoundary } from '@/components/errors/QueryErrorBoundary';
import { cn } from '@/lib/utils';
import { withApiBaseForRequest } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import type { CreateConversationResponse } from '@/types/conversation';

interface ChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  conversationId?: string;
  bookingId?: string;
  instructorId?: string;
  currentUserId: string;
  currentUserName: string;
  otherUserName: string;
  lessonTitle?: string;
  lessonDate?: string;
  isReadOnly?: boolean;
}

const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

export function ChatModal({
  isOpen,
  onClose,
  conversationId,
  bookingId,
  instructorId,
  currentUserId,
  currentUserName,
  otherUserName,
  lessonTitle,
  lessonDate,
  isReadOnly = false,
}: ChatModalProps) {
  const modalRef = useRef<HTMLDivElement | null>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  const getFocusableElements = useCallback((): HTMLElement[] => {
    if (!modalRef.current) return [];
    const elements = Array.from(modalRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    return elements.filter((element) => {
      if (element.getAttribute('aria-hidden') === 'true') return false;
      if (element.hasAttribute('hidden')) return false;
      if (element.tabIndex < 0) return false;
      if (element instanceof HTMLButtonElement && element.disabled) return false;
      if (element instanceof HTMLInputElement && element.disabled) return false;
      if (element instanceof HTMLSelectElement && element.disabled) return false;
      if (element instanceof HTMLTextAreaElement && element.disabled) return false;
      return true;
    });
  }, []);

  // Handle keyboard and focus management
  useEffect(() => {
    if (!isOpen) return;

    previousActiveElementRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const focusableElements = getFocusableElements();
    const firstFocusableElement = focusableElements[0];
    if (firstFocusableElement) {
      firstFocusableElement.focus();
    } else {
      modalRef.current?.focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key !== 'Tab') return;

      const modalElement = modalRef.current;
      if (!modalElement) return;

      const currentFocusableElements = getFocusableElements();
      if (!currentFocusableElements.length) {
        e.preventDefault();
        modalElement.focus();
        return;
      }

      const firstElement = currentFocusableElements[0];
      const lastElement = currentFocusableElements[currentFocusableElements.length - 1];
      const activeElement = document.activeElement as HTMLElement | null;

      if (!activeElement || !modalElement.contains(activeElement)) {
        e.preventDefault();
        (e.shiftKey ? lastElement : firstElement)?.focus();
        return;
      }

      if (e.shiftKey && activeElement === firstElement) {
        e.preventDefault();
        lastElement?.focus();
        return;
      }

      if (!e.shiftKey && activeElement === lastElement) {
        e.preventDefault();
        firstElement?.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = originalOverflow;

      const previousActiveElement = previousActiveElementRef.current;
      if (
        previousActiveElement &&
        document.contains(previousActiveElement) &&
        typeof previousActiveElement.focus === 'function'
      ) {
        previousActiveElement.focus();
      }
    };
  }, [getFocusableElements, isOpen, onClose]);

  const { data: conversationData, isLoading: isLoadingConversation } = useQuery({
    queryKey: ['conversation-for-instructor', instructorId],
    queryFn: async () => {
      const response = await fetchWithSessionRefresh(withApiBaseForRequest('/api/v1/conversations', 'POST'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ instructor_id: instructorId }),
      });
      if (!response.ok) {
        throw new Error('Failed to get conversation');
      }
      return response.json() as Promise<CreateConversationResponse>;
    },
    enabled: !conversationId && !!instructorId,
    staleTime: Infinity,
  });

  const resolvedConversationId = conversationId ?? conversationData?.id ?? null;

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm transition-opacity dark:bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal/Drawer */}
      <div
        ref={modalRef}
        className={cn(
          'fixed z-50 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80 shadow-2xl transition-all border border-gray-300 overflow-hidden flex h-full flex-col',
          'dark:bg-gray-900/90 dark:supports-[backdrop-filter]:bg-gray-900/75 dark:border-gray-600 dark:shadow-xl',
          // Mobile: Full-screen drawer from bottom
          'inset-x-0 bottom-0 h-[92dvh] rounded-3xl',
          // Portrait phones: center the modal
          'portrait:inset-auto portrait:left-1/2 portrait:top-1/2 portrait:-translate-x-1/2 portrait:-translate-y-1/2 portrait:h-[85dvh] portrait:w-[92vw] portrait:max-w-md',
          // Desktop: Centered modal
          'sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2',
          'sm:h-[80vh] sm:w-[90vw] sm:max-w-2xl sm:rounded-3xl'
        )}
        role="dialog"
        aria-modal="true"
        aria-label="Chat"
        tabIndex={-1}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-4 pt-5 pb-3 sm:px-6 sm:pt-6 sm:pb-4 dark:border-gray-800 pt-[max(env(safe-area-inset-top),theme(spacing.5))] bg-[#EDE7F6]">
          <div className="flex-1">
            <h2 className="text-base sm:text-lg font-bold text-gray-900 tracking-tight dark:text-gray-100">
              Chat with {otherUserName}
            </h2>
            {lessonTitle && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {lessonTitle}
                {lessonDate && ` • ${lessonDate}`}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 hover:bg-gray-100 transition-colors ring-1 ring-transparent hover:ring-gray-200 dark:hover:bg-gray-800 dark:hover:ring-gray-700"
            aria-label="Close chat"
          >
            <X className="h-5 w-5 text-gray-500 dark:text-gray-400" aria-hidden="true" />
          </button>
        </div>

        {/* Chat component - wrapped in error boundary for graceful error handling */}
        {resolvedConversationId && (
          <QueryErrorBoundary>
            <Chat
              conversationId={resolvedConversationId}
              {...(bookingId ? { bookingId } : {})}
              currentUserId={currentUserId}
              currentUserName={currentUserName}
              otherUserName={otherUserName}
              className="flex-1 min-h-0"
              onClose={onClose}
              isReadOnly={isReadOnly}
            />
          </QueryErrorBoundary>
        )}
        {!resolvedConversationId && isLoadingConversation && (
          <div className="flex flex-1 items-center justify-center text-sm text-gray-500">
            Loading conversation...
          </div>
        )}
      </div>
    </>
  );
}
