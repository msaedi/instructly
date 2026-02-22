'use client';

import React, { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { logger } from '@/lib/logger';

export interface VideoErrorBoundaryProps {
  onLeave: () => void;
  fallbackPath?: string;
  redirectToPath?: (path: string) => void;
  children: ReactNode;
}

interface VideoErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  countdown: number;
  recoverable: boolean;
  retryCount: number;
}

const AUTO_REDIRECT_SECONDS = 3;
const DEFAULT_FALLBACK_PATH = '/student/lessons';
const KNOWN_PORTAL_ERROR_PATTERN = 'getComputedStyle';
const MAX_RECOVERIES = 3;
const CRASH_LOOP_WINDOW_MS = 30_000;
const RECOVERY_DELAY_MS = 1500;

function isKnownPortalError(error: Error): boolean {
  return error.message.includes(KNOWN_PORTAL_ERROR_PATTERN);
}

export class VideoErrorBoundary extends Component<VideoErrorBoundaryProps, VideoErrorBoundaryState> {
  private _timerId: ReturnType<typeof setInterval> | null = null;
  private _recoveryTimerId: ReturnType<typeof setTimeout> | null = null;
  private _errorTimestamps: number[] = [];

  constructor(props: VideoErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      countdown: AUTO_REDIRECT_SECONDS,
      recoverable: false,
      retryCount: 0,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<VideoErrorBoundaryState> {
    return {
      hasError: true,
      error,
      countdown: AUTO_REDIRECT_SECONDS,
      recoverable: isKnownPortalError(error),
    };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logger.error('Video SDK crashed', error, {
      componentStack: errorInfo.componentStack,
    });

    if (this.state.recoverable) {
      this._errorTimestamps.push(Date.now());
      const cutoff = Date.now() - CRASH_LOOP_WINDOW_MS;
      this._errorTimestamps = this._errorTimestamps.filter((t) => t > cutoff);

      if (this._errorTimestamps.length >= MAX_RECOVERIES) {
        this.setState({ recoverable: false });
        this._startCountdown();
        return;
      }

      this._recoveryTimerId = setTimeout(() => {
        this.setState((prev) => ({
          hasError: false,
          error: null,
          recoverable: false,
          retryCount: prev.retryCount + 1,
          countdown: AUTO_REDIRECT_SECONDS,
        }));
      }, RECOVERY_DELAY_MS);
    } else {
      this._startCountdown();
    }
  }

  override componentWillUnmount() {
    this._clearTimer();
    if (this._recoveryTimerId !== null) {
      clearTimeout(this._recoveryTimerId);
      this._recoveryTimerId = null;
    }
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
      const path = this.props.fallbackPath ?? DEFAULT_FALLBACK_PATH;
      if (this.props.redirectToPath) {
        this.props.redirectToPath(path);
        return;
      }
      window.location.href = path;
    }
  };

  override render() {
    if (this.state.hasError) {
      if (this.state.recoverable) {
        return (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
            <div className="bg-white rounded-xl shadow-lg p-8 text-center max-w-sm animate-fade-in">
              <p className="text-muted-foreground">
                A dialog crashed. Returning to your lesson…
              </p>
            </div>
          </div>
        );
      }

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
            className="rounded-lg bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-purple-800 transition-colors"
          >
            Back to My Lessons
          </button>
        </div>
      );
    }

    return (
      <React.Fragment key={this.state.retryCount}>
        {this.props.children}
      </React.Fragment>
    );
  }
}
