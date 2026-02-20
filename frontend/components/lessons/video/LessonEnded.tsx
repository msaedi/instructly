import Link from 'next/link';
import { Card } from '@/components/ui/card';
import { CheckCircle2, Clock, User as UserIcon } from 'lucide-react';
import type { Booking, VideoSessionStatusResponse } from '@/features/shared/api/types';

interface LessonEndedProps {
  booking: Booking;
  sessionData?: VideoSessionStatusResponse | null;
  userRole: 'student' | 'instructor';
  localJoinedAt?: string | null;
  localLeftAt?: string | null;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function computeLocalDuration(joinedAt: string | null | undefined, leftAt: string | null | undefined): string {
  if (!joinedAt || !leftAt) return '--';
  const ms = new Date(leftAt).getTime() - new Date(joinedAt).getTime();
  if (!Number.isFinite(ms) || ms <= 0) return '--';
  return formatDuration(Math.floor(ms / 1000));
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '--';
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '--';
  }
}

export function LessonEnded({ booking, sessionData, userRole, localJoinedAt, localLeftAt }: LessonEndedProps) {
  const backHref = userRole === 'instructor' ? '/instructor/bookings' : '/student/lessons';

  // Duration: prefer backend, fall back to client-side computation
  const duration = booking.video_session_duration_seconds
    ? formatDuration(booking.video_session_duration_seconds)
    : computeLocalDuration(localJoinedAt, localLeftAt);

  // Join times: prefer backend webhook data, fall back to local timestamp for own role only
  const instructorJoinedDisplay = formatTime(
    sessionData?.instructor_joined_at ?? (userRole === 'instructor' ? localJoinedAt : null),
  );
  const studentJoinedDisplay = formatTime(
    sessionData?.student_joined_at ?? (userRole === 'student' ? localJoinedAt : null),
  );

  return (
    <div className="flex items-center justify-center px-4 py-12">
      <Card className="w-full max-w-md bg-white rounded-xl shadow-lg p-8">
        <div className="flex flex-col items-center gap-6 text-center">
          <CheckCircle2 className="h-12 w-12 text-emerald-500" aria-hidden="true" />

          <div>
            <h1 className="text-2xl font-semibold text-[#7E22CE]">Lesson Complete</h1>
            <p className="mt-1 text-muted-foreground">{booking.service_name}</p>
          </div>

          <div role="status" aria-label="Session summary" className="w-full space-y-3">
            <div className="flex items-center gap-3 text-sm">
              <Clock className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="text-muted-foreground">Duration</span>
              <span className="ml-auto font-medium text-foreground">{duration}</span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <UserIcon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="text-muted-foreground">Instructor joined</span>
              <span className="ml-auto font-medium text-foreground">{instructorJoinedDisplay}</span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <UserIcon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="text-muted-foreground">Student joined</span>
              <span className="ml-auto font-medium text-foreground">{studentJoinedDisplay}</span>
            </div>
          </div>

          <div className="w-full border-t border-gray-200" />

          <div className="flex gap-4">
            <Link
              href={backHref}
              className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-purple-800 transition-colors"
            >
              Back to My Lessons
            </Link>
            {userRole === 'student' && booking.instructor_id && (
              <Link
                href={`/instructors/${booking.instructor_id}`}
                className="rounded-lg border border-border px-6 py-2 text-sm font-medium hover:bg-accent transition-colors"
              >
                Book Again
              </Link>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
