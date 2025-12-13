/**
 * MessageInstructorButton - Button to start a conversation with an instructor
 *
 * Phase 6: Enables pre-booking messaging by creating a conversation and
 * navigating to the messages page.
 */

'use client';

import { MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { cn } from '@/lib/utils';

export interface MessageInstructorButtonProps {
  /** Instructor's user ID */
  instructorId: string;
  /** Instructor's display name (for accessibility) */
  instructorName: string;
  /** Button variant */
  variant?: 'default' | 'outline' | 'secondary' | 'ghost';
  /** Button size */
  size?: 'default' | 'sm' | 'lg';
  /** Show full text or just icon */
  iconOnly?: boolean;
  /** Custom class names */
  className?: string;
}

export function MessageInstructorButton({
  instructorId,
  instructorName,
  variant = 'outline',
  size = 'default',
  iconOnly = false,
  className,
}: MessageInstructorButtonProps) {
  const { createConversation, isCreating } = useCreateConversation();
  const { user, isAuthenticated, redirectToLogin } = useAuth();

  const handleClick = async () => {
    if (!isAuthenticated) {
      // Redirect to login with return URL to instructor profile
      redirectToLogin(`/instructors/${instructorId}`);
      return;
    }

    // Don't allow instructor to message themselves
    if (user?.id === instructorId) {
      return;
    }

    await createConversation(instructorId, { navigateToMessages: true });
  };

  // Don't show button if user is the instructor
  if (user?.id === instructorId) {
    return null;
  }

  const buttonText = isCreating ? 'Opening...' : 'Message';
  const ariaLabel = `Message ${instructorName}`;

  return (
    <Button
      onClick={handleClick}
      disabled={isCreating}
      variant={variant}
      size={size}
      className={cn(
        'gap-2',
        // Ensure good touch target on mobile (min 44px)
        size === 'sm' && 'min-h-[44px]',
        className
      )}
      aria-label={ariaLabel}
    >
      <MessageSquare className={cn('h-4 w-4', size === 'lg' && 'h-5 w-5')} />
      {!iconOnly && <span>{buttonText}</span>}
    </Button>
  );
}
