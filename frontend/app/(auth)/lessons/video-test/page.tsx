'use client';

import { useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { VideoErrorBoundary } from '@/components/lessons/video/VideoErrorBoundary';

// Dev/QA testing page — renders HMSPrebuilt with hardcoded room codes,
// bypassing booking lookup, advance notice, and time constraints.
// Access restricted to specific test accounts.

const HMSPrebuilt = dynamic(
  () => import('@100mslive/roomkit-react').then((m) => m.HMSPrebuilt),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    ),
  },
);

const ALLOWED_EMAILS = ['sarah.chen@example.com', 'emma.johnson@example.com'];

const HOST_ROOM_CODE = process.env['NEXT_PUBLIC_100MS_TEST_ROOM_CODE_HOST'] ?? '';
const GUEST_ROOM_CODE = process.env['NEXT_PUBLIC_100MS_TEST_ROOM_CODE_GUEST'] ?? '';

export default function VideoTestPage() {
  const { user, isLoading } = useAuth();
  const searchParams = useSearchParams();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!user || !ALLOWED_EMAILS.includes(user.email)) {
    return (
      <div className="flex h-screen items-center justify-center px-4">
        <p className="text-muted-foreground">Access denied — this page is restricted to test accounts.</p>
      </div>
    );
  }

  if (!HOST_ROOM_CODE || !GUEST_ROOM_CODE) {
    return (
      <div className="flex h-screen items-center justify-center px-4">
        <p className="text-muted-foreground">
          Test page not available — room codes not configured.
          Set NEXT_PUBLIC_100MS_TEST_ROOM_CODE_HOST and NEXT_PUBLIC_100MS_TEST_ROOM_CODE_GUEST in .env.local.
        </p>
      </div>
    );
  }

  const role = searchParams.get('role') === 'host' ? 'host' : 'guest';
  const roomCode = role === 'host' ? HOST_ROOM_CODE : GUEST_ROOM_CODE;

  const handleLeave = () => {
    window.location.href = '/student/lessons';
  };

  return (
    <VideoErrorBoundary onLeave={handleLeave}>
      <div role="main" aria-label="Video test session" className="fixed inset-0 z-50 bg-background">
        <HMSPrebuilt
          roomCode={roomCode}
          options={{ userName: user.first_name, userId: user.id }}
          onLeave={handleLeave}
        />
      </div>
    </VideoErrorBoundary>
  );
}
