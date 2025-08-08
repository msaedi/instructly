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
  bookingId: number;
  currentUserId: number;
  currentUserName: string;
  otherUserName: string;
  lessonTitle?: string;
  lessonDate?: string;
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
        className="fixed inset-0 z-50 bg-black/50 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal/Drawer */}
      <div
        className={cn(
          'fixed z-50 bg-white shadow-xl transition-all',
          // Mobile: Full-screen drawer from bottom
          'inset-x-0 bottom-0 h-[90vh] rounded-t-2xl',
          // Desktop: Centered modal
          'sm:inset-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2',
          'sm:h-[80vh] sm:w-[90vw] sm:max-w-2xl sm:rounded-2xl'
        )}
        role="dialog"
        aria-modal="true"
        aria-label="Chat"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-4 py-3 sm:px-6">
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-gray-900">
              Chat with {otherUserName}
            </h2>
            {lessonTitle && (
              <p className="text-sm text-gray-500">
                {lessonTitle}
                {lessonDate && ` • ${lessonDate}`}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 hover:bg-gray-100 transition-colors"
            aria-label="Close chat"
          >
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {/* Chat component - only render when fully mounted */}
        {isMounted && (
          <Chat
            bookingId={bookingId}
            currentUserId={currentUserId}
            currentUserName={currentUserName}
            otherUserName={otherUserName}
            className="h-[calc(100%-60px)]"
            onClose={onClose}
          />
        )}
      </div>
    </>
  );
}
