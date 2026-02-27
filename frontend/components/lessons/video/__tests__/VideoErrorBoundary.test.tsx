import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';

jest.mock('@/lib/logger', () => ({
  logger: { error: jest.fn(), debug: jest.fn(), warn: jest.fn(), info: jest.fn() },
}));

import { VideoErrorBoundary } from '../VideoErrorBoundary';

/**
 * Helper that renders a child component which throws on demand.
 * We control throwing via a module-level flag so re-renders
 * after recovery can succeed.
 */
let shouldChildThrow = false;
let childError: Error | null = null;

function ThrowingChild() {
  if (childError) throw childError;
  if (shouldChildThrow) throw new Error('SDK crash');
  return <div data-testid="child">OK</div>;
}

describe('VideoErrorBoundary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    shouldChildThrow = false;
    childError = null;
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('renders children when no error occurs', () => {
    render(
      <VideoErrorBoundary onLeave={jest.fn()}>
        <ThrowingChild />
      </VideoErrorBoundary>,
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('shows error fallback with countdown when child throws a non-recoverable error', () => {
    shouldChildThrow = true;
    render(
      <VideoErrorBoundary onLeave={jest.fn()}>
        <ThrowingChild />
      </VideoErrorBoundary>,
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/video session encountered an error/i)).toBeInTheDocument();
    expect(screen.getByText(/redirecting in 3 seconds/i)).toBeInTheDocument();
  });

  it('calls onLeave when Back to My Lessons button is clicked', () => {
    shouldChildThrow = true;
    const onLeave = jest.fn();
    render(
      <VideoErrorBoundary onLeave={onLeave}>
        <ThrowingChild />
      </VideoErrorBoundary>,
    );

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it('uses redirectToPath with default fallback path when onLeave throws', () => {
    shouldChildThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('onLeave failed');
    });
    const redirectToPath = jest.fn();

    render(
      <VideoErrorBoundary onLeave={onLeave} redirectToPath={redirectToPath}>
        <ThrowingChild />
      </VideoErrorBoundary>,
    );

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(redirectToPath).toHaveBeenCalledWith('/student/lessons');
  });

  it('uses redirectToPath with custom fallbackPath when onLeave throws', () => {
    shouldChildThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('onLeave failed');
    });
    const redirectToPath = jest.fn();

    render(
      <VideoErrorBoundary
        onLeave={onLeave}
        fallbackPath="/instructor/dashboard"
        redirectToPath={redirectToPath}
      >
        <ThrowingChild />
      </VideoErrorBoundary>,
    );

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(redirectToPath).toHaveBeenCalledWith('/instructor/dashboard');
  });

  it('falls back to window.location.href when onLeave throws and no redirectToPath is provided', () => {
    shouldChildThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('onLeave failed');
    });
    // Suppress JSDOM "Not implemented: navigation" error
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <VideoErrorBoundary onLeave={onLeave}>
        <ThrowingChild />
      </VideoErrorBoundary>,
    );

    // Click should not throw -- exercises window.location.href = path (line 130)
    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);

    consoleSpy.mockRestore();
  });

  it('falls back to window.location.href with custom fallbackPath when no redirectToPath', () => {
    shouldChildThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('onLeave failed');
    });
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <VideoErrorBoundary onLeave={onLeave} fallbackPath="/custom/path">
        <ThrowingChild />
      </VideoErrorBoundary>,
    );

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
    // Exercises catch block with fallbackPath but no redirectToPath (line 125-130)

    consoleSpy.mockRestore();
  });

  it('auto-redirects via countdown when onLeave throws and no redirectToPath', () => {
    jest.useFakeTimers();
    shouldChildThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('onLeave failed');
    });
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <VideoErrorBoundary onLeave={onLeave}>
        <ThrowingChild />
      </VideoErrorBoundary>,
    );

    // Countdown from 3
    act(() => { jest.advanceTimersByTime(1000); });
    act(() => { jest.advanceTimersByTime(1000); });
    act(() => { jest.advanceTimersByTime(1000); });

    // onLeave should have been called by auto-redirect
    expect(onLeave).toHaveBeenCalledTimes(1);
    // Since onLeave throws and no redirectToPath, window.location.href is set (line 130)

    consoleSpy.mockRestore();
  });
});
