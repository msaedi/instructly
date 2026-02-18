import Link from 'next/link';
import type { Booking, VideoSessionStatusResponse } from '@/features/shared/api/types';

interface LessonEndedProps {
  booking: Booking;
  sessionData?: VideoSessionStatusResponse | null;
  userRole: 'student' | 'instructor';
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

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '--';
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '--';
  }
}

export function LessonEnded({ booking, sessionData, userRole }: LessonEndedProps) {
  const backHref = userRole === 'instructor' ? '/instructor/bookings' : '/student/lessons';

  return (
    <div role="status" aria-label="Lesson ended" className="flex flex-col items-center justify-center gap-6 py-12 px-4 text-center">
      <h1 className="text-2xl font-semibold">Lesson Complete</h1>
      <p className="text-muted-foreground">{booking.service_name}</p>

      {sessionData && (
        <div className="flex flex-col gap-2 text-sm text-muted-foreground">
          <p>
            Duration:{' '}
            <span className="font-medium text-foreground">
              {formatDuration(booking.video_session_duration_seconds)}
            </span>
          </p>
          <p>
            Instructor joined:{' '}
            <span className="font-medium text-foreground">
              {formatTime(sessionData.instructor_joined_at)}
            </span>
          </p>
          <p>
            Student joined:{' '}
            <span className="font-medium text-foreground">
              {formatTime(sessionData.student_joined_at)}
            </span>
          </p>
        </div>
      )}

      <div className="flex gap-4">
        <Link
          href={backHref}
          className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
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
  );
}
