'use client';

import dynamic from 'next/dynamic';

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

interface ActiveLessonProps {
  authToken: string;
  userName: string;
  userId: string;
  onLeave: () => void;
}

export function ActiveLesson({ authToken, userName, userId, onLeave }: ActiveLessonProps) {
  return (
    <div role="main" aria-label="Video lesson in progress" className="fixed inset-0 z-50 bg-background">
      <HMSPrebuilt
        authToken={authToken}
        options={{ userName, userId }}
        onLeave={onLeave}
      />
    </div>
  );
}
