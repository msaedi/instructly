'use client';

import { useCountdown } from '@/hooks/useCountdown';
import { Card } from '@/components/ui/card';
import { User as UserIcon } from 'lucide-react';
import type { Booking } from '@/features/shared/api/types';

interface PreLessonWaitingProps {
  booking: Booking;
  userName: string;
  otherPartyName: string;
  otherPartyRole: 'student' | 'instructor';
  onJoin: () => void;
  isJoining: boolean;
  joinError: string | null;
}

function CountdownPill({ secondsLeft, formatted }: { secondsLeft: number; formatted: string }) {
  let colorClasses = 'bg-gray-100 text-gray-700';
  if (secondsLeft <= 60) {
    colorClasses = 'bg-red-100 text-red-700';
  } else if (secondsLeft <= 300) {
    colorClasses = 'bg-amber-100 text-amber-700';
  }

  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-sm font-medium tabular-nums ${colorClasses}`}>
      Window closes in {formatted}
    </span>
  );
}

export function PreLessonWaiting({
  booking,
  userName,
  otherPartyName,
  otherPartyRole,
  onJoin,
  isJoining,
  joinError,
}: PreLessonWaitingProps) {
  const opensCountdown = useCountdown(booking.join_opens_at ?? null);
  const closesCountdown = useCountdown(booking.join_closes_at ?? null);

  const windowOpen = opensCountdown.isExpired && !closesCountdown.isExpired;
  const windowClosed = opensCountdown.isExpired && closesCountdown.isExpired;

  return (
    <div className="flex items-center justify-center px-4 py-12">
      {/* bg-white explicit: CSS --card maps to lavender, but we want white to match LessonCard */}
      <Card className="w-full max-w-md bg-white rounded-xl shadow-lg p-8">
        <div className="flex flex-col items-center gap-6 text-center">
          <h1 className="text-2xl font-semibold text-[#7E22CE]">{booking.service_name}</h1>

          <p className="text-muted-foreground">
            {otherPartyRole === 'instructor'
              ? `Your instructor: ${otherPartyName}`
              : `Your student: ${otherPartyName}`}
          </p>

          {!opensCountdown.isExpired && (
            <div className="flex flex-col items-center gap-2">
              <p className="text-sm text-muted-foreground">Join opens in</p>
              <p className="text-4xl font-mono font-bold tabular-nums" aria-live="polite" role="timer">
                {opensCountdown.formatted}
              </p>
            </div>
          )}

          {windowOpen && (
            <div className="flex flex-col items-center gap-3">
              <CountdownPill secondsLeft={closesCountdown.secondsLeft} formatted={closesCountdown.formatted} />
              <button
                type="button"
                onClick={onJoin}
                disabled={isJoining}
                aria-label="Join video lesson"
                aria-busy={isJoining}
                className="animate-pulse-join rounded-lg bg-primary px-8 py-3 text-lg font-semibold text-primary-foreground hover:bg-purple-800 transition-colors disabled:opacity-50"
              >
                <span className="inline-flex items-center gap-2">
                  {isJoining && (
                    <span
                      className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent"
                      aria-hidden="true"
                    />
                  )}
                  {isJoining ? 'Connecting...' : 'Join Lesson'}
                </span>
              </button>
            </div>
          )}

          {windowClosed && (
            <p className="text-sm text-destructive font-medium">
              Join window has closed.
            </p>
          )}

          {joinError && (
            <p className="text-sm text-destructive" role="alert">
              {joinError}
            </p>
          )}

          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <UserIcon className="h-4 w-4" aria-hidden="true" />
            <span>Joining as {userName}</span>
          </div>
        </div>
      </Card>
    </div>
  );
}
