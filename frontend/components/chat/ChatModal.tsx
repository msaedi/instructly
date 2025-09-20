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

import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { Chat } from './Chat';
import { cn } from '@/lib/utils';

interface ChatModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookingId: string;
  currentUserId: string;
  currentUserName: string;
  otherUserName: string;
  lessonTitle?: string;
  lessonDate?: string;
  isReadOnly?: boolean;
}

export function ChatModal({
  isOpen,
  onClose,
  bookingId,
  currentUserId,
  currentUserName,
  otherUserName,
  lessonTitle,
  lessonDate,
  isReadOnly = false,
}: ChatModalProps) {
  const [isMounted, setIsMounted] = useState(false);

  // Handle escape key and mounting
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // Prevent body scroll on mobile
      document.body.style.overflow = 'hidden';
      // Delay mounting the Chat component slightly to ensure modal is ready
      const mountTimer = setTimeout(() => setIsMounted(true), 50);

      return () => {
        clearTimeout(mountTimer);
        document.removeEventListener('keydown', handleEscape);
        document.body.style.overflow = '';
        setIsMounted(false);
      };
    } else {
      setIsMounted(false);
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

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

        {/* Chat component - only render when fully mounted */}
        {isMounted && (
          <Chat
            bookingId={bookingId}
            currentUserId={currentUserId}
            currentUserName={currentUserName}
            otherUserName={otherUserName}
            className="flex-1 min-h-0"
            onClose={onClose}
            isReadOnly={isReadOnly}
          />
        )}
      </div>
    </>
  );
}
