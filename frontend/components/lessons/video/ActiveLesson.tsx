'use client';

import dynamic from 'next/dynamic';
import { VideoErrorBoundary } from './VideoErrorBoundary';

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

const DEFAULT_FALLBACK_PATH = '/student/lessons';

interface ActiveLessonProps {
  authToken: string;
  userName: string;
  userId: string;
  onJoin?: () => void;
  onLeave: () => void;
  fallbackPath?: string;
  redirectToPath?: (path: string) => void;
}

export function ActiveLesson({
  authToken,
  userName,
  userId,
  onJoin,
  onLeave,
  fallbackPath,
  redirectToPath,
}: ActiveLessonProps) {
  const handleBackToLessons = () => {
    try {
      onLeave();
    } catch {
      const path = fallbackPath ?? DEFAULT_FALLBACK_PATH;
      if (redirectToPath) {
        redirectToPath(path);
        return;
      }
      window.location.href = path;
    }
  };

  if (!authToken) {
    return (
      <div role="alert" className="flex flex-col items-center justify-center gap-6 py-16 px-4 text-center">
        <p className="text-lg text-muted-foreground">
          Unable to connect to lesson room. Please try again.
        </p>
        <button
          type="button"
          onClick={handleBackToLessons}
          className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-purple-800 transition-colors"
        >
          Back to My Lessons
        </button>
      </div>
    );
  }

  return (
    <VideoErrorBoundary
      onLeave={onLeave}
      {...(fallbackPath !== undefined ? { fallbackPath } : {})}
      {...(redirectToPath !== undefined ? { redirectToPath } : {})}
    >
      <div role="main" aria-label="Video lesson in progress" className="fixed inset-0 z-50 bg-background">
        <HMSPrebuilt
          authToken={authToken}
          options={{ userName, userId }}
          {...(onJoin !== undefined ? { onJoin } : {})}
          onLeave={onLeave}
        />
      </div>
    </VideoErrorBoundary>
  );
}
