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
        className={buttonVariants({ variant: 'default', size: 'sm' }) + ' animate-pulse-join' + (className ? ` ${className}` : '')}
        data-testid="join-lesson-button"
      >
        <Video className="mr-1.5 h-4 w-4" />
        Join Lesson
      </Link>
    );
  }

  // Before the window opens, keep the CTA visible and explain when it activates.
  if (!opensCountdown.isExpired) {
    return (
      <div className={className}>
        <div className="flex flex-col items-start gap-1">
          <button
            type="button"
            disabled
            aria-label="Join video lesson"
            data-testid="join-lesson-button"
            className="inline-flex h-9 min-w-[116px] cursor-not-allowed items-center justify-center rounded-md bg-[#F3F4F6] px-3 text-sm font-medium text-[#9CA3AF]"
          >
            <Video className="mr-1.5 h-4 w-4" />
            Join Lesson
          </button>
          <p
            className="text-xs text-gray-500 dark:text-gray-400 tabular-nums"
            data-testid="join-lesson-countdown"
            aria-live="polite"
          >
            Join opens in {opensCountdown.formatted}
          </p>
        </div>
      </div>
    );
  }

  // After the scheduled session end — don't show button
  return null;
}
