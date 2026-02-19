'use client';

import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { logger } from '@/lib/logger';

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

interface VideoErrorBoundaryProps {
  onLeave: () => void;
  children: ReactNode;
}

interface VideoErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  countdown: number;
}

const AUTO_REDIRECT_SECONDS = 3;

class VideoErrorBoundary extends Component<VideoErrorBoundaryProps, VideoErrorBoundaryState> {
  private _timerId: ReturnType<typeof setInterval> | null = null;

  constructor(props: VideoErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, countdown: AUTO_REDIRECT_SECONDS };
  }

  static getDerivedStateFromError(error: Error): VideoErrorBoundaryState {
    return { hasError: true, error, countdown: AUTO_REDIRECT_SECONDS };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // logger.error routes to Sentry.captureException via lib/logger
    logger.error('Video SDK crashed', error, {
      componentStack: errorInfo.componentStack,
    });

    // SDK cleanup: HMSPrebuilt unmounts when this fallback renders, which
    // triggers the SDK's internal room disconnect. No explicit leave() call
    // is possible — useHMSActions() requires HMSRoomProvider context that
    // this boundary sits outside of.

    this._startCountdown();
  }

  override componentWillUnmount() {
    this._clearTimer();
  }

  private _startCountdown() {
    this._clearTimer();
    this._timerId = setInterval(() => {
      this.setState(
        (prev): VideoErrorBoundaryState => ({
          ...prev,
          countdown: prev.countdown - 1,
        }),
        () => {
          if (this.state.countdown <= 0) {
            this._safeLeave();
          }
        },
      );
    }, 1000);
  }

  private _clearTimer() {
    if (this._timerId !== null) {
      clearInterval(this._timerId);
      this._timerId = null;
    }
  }

  private _safeLeave = () => {
    this._clearTimer();
    try {
      this.props.onLeave();
    } catch {
      window.location.href = '/lessons';
    }
  };

  override render() {
    if (this.state.hasError) {
      return (
        <div role="alert" className="flex flex-col items-center justify-center gap-6 py-16 px-4 text-center">
          <p className="text-lg text-muted-foreground">
            The video session encountered an error.
          </p>
          <p className="text-sm text-muted-foreground">
            Redirecting in {this.state.countdown} {this.state.countdown === 1 ? 'second' : 'seconds'}…
          </p>
          <button
            type="button"
            onClick={this._safeLeave}
            className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Back to My Lessons
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

interface ActiveLessonProps {
  authToken: string;
  userName: string;
  userId: string;
  onLeave: () => void;
}

export function ActiveLesson({ authToken, userName, userId, onLeave }: ActiveLessonProps) {
  if (!authToken) {
    return (
      <div role="alert" className="flex flex-col items-center justify-center gap-6 py-16 px-4 text-center">
        <p className="text-lg text-muted-foreground">
          Unable to connect to lesson room. Please try again.
        </p>
        <button
          type="button"
          onClick={onLeave}
          className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          Back to My Lessons
        </button>
      </div>
    );
  }

  return (
    <VideoErrorBoundary onLeave={onLeave}>
      <div role="main" aria-label="Video lesson in progress" className="fixed inset-0 z-50 bg-background">
        <HMSPrebuilt
          authToken={authToken}
          options={{ userName, userId }}
          onLeave={onLeave}
        />
      </div>
    </VideoErrorBoundary>
  );
}
