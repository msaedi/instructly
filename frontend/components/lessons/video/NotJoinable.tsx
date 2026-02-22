import Link from 'next/link';

export type NotJoinableReason = 'in-person' | 'cancelled' | 'not-available';

const MESSAGES: Record<NotJoinableReason, string> = {
  'in-person': 'This is an in-person lesson. Video is not available.',
  cancelled: 'This lesson was cancelled.',
  'not-available': 'Video is not available for this lesson.',
};

interface NotJoinableProps {
  reason: NotJoinableReason;
  userRole: 'student' | 'instructor';
}

export function NotJoinable({ reason, userRole }: NotJoinableProps) {
  const backHref = userRole === 'instructor' ? '/instructor/bookings' : '/student/lessons';

  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-6 py-16 px-4 text-center">
      <p className="text-lg text-muted-foreground">{MESSAGES[reason]}</p>
      <Link
        href={backHref}
        className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-purple-800 transition-colors"
      >
        Back to My Lessons
      </Link>
    </div>
  );
}
