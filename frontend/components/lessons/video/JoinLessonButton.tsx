import Link from 'next/link';
import { Video } from 'lucide-react';
import { useCountdown } from '@/hooks/useCountdown';
import { buttonVariants } from '@/components/ui/button.utils';

interface JoinLessonButtonProps {
  bookingId: string;
  joinOpensAt: string | null | undefined;
  joinClosesAt: string | null | undefined;
  className?: string;
}

export function JoinLessonButton({
  bookingId,
  joinOpensAt,
  joinClosesAt,
  className,
}: JoinLessonButtonProps) {
  const opensCountdown = useCountdown(joinOpensAt ?? null);
  const closesCountdown = useCountdown(joinClosesAt ?? null);

  // Not applicable (in-person, feature disabled, etc.)
  if (!joinOpensAt) return null;

  // Window is open: opens has expired but closes hasn't yet
  if (opensCountdown.isExpired && !closesCountdown.isExpired) {
    return (
      <Link
        href={`/lessons/${bookingId}`}
        aria-label="Join video lesson"
        className={buttonVariants({ variant: 'success', size: 'sm' }) + (className ? ` ${className}` : '')}
        data-testid="join-lesson-button"
      >
        <Video className="mr-1.5 h-4 w-4" />
        Join Lesson
      </Link>
    );
  }

  // Before window or after window — don't show button
  return null;
}
