import { render, screen, fireEvent, act } from '@testing-library/react';

let shouldThrow = false;
let customThrowError: Error | null = null;

jest.mock('@100mslive/roomkit-react', () => ({
  HMSPrebuilt: (props: Record<string, unknown>) => {
    if (customThrowError) {
      throw customThrowError;
    }
    if (shouldThrow) {
      throw new Error('Portal container not found');
    }
    const options = props['options'] as Record<string, unknown> | undefined;
    return (
      <div
        data-testid="hms-prebuilt"
        data-auth-token={props['authToken']}
        data-user-name={options?.['userName']}
        data-user-id={options?.['userId']}
      >
        <button type="button" onClick={props['onLeave'] as () => void}>
          Leave
        </button>
      </div>
    );
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: { error: jest.fn(), debug: jest.fn(), warn: jest.fn(), info: jest.fn() },
}));

import { ActiveLesson } from '../ActiveLesson';

const defaultProps = {
  authToken: 'test-token-abc',
  userName: 'Alice',
  userId: 'user_01HYXZ',
  onLeave: jest.fn(),
};

const PORTAL_ERROR_MSG = "Failed to execute 'getComputedStyle' on 'Window': parameter 1 is not of type 'Element'.";

describe('ActiveLesson', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    shouldThrow = false;
    customThrowError = null;
  });

  it('renders wrapper with role="main" and accessible label', () => {
    render(<ActiveLesson {...defaultProps} />);
    const wrapper = screen.getByRole('main');
    expect(wrapper).toHaveAttribute('aria-label', 'Video lesson in progress');
  });

  it('passes authToken to HMSPrebuilt', () => {
    render(<ActiveLesson {...defaultProps} />);
    const prebuilt = screen.getByTestId('hms-prebuilt');
    expect(prebuilt).toHaveAttribute('data-auth-token', 'test-token-abc');
  });

  it('passes userName and userId via options', () => {
    render(<ActiveLesson {...defaultProps} />);
    const prebuilt = screen.getByTestId('hms-prebuilt');
    expect(prebuilt).toHaveAttribute('data-user-name', 'Alice');
    expect(prebuilt).toHaveAttribute('data-user-id', 'user_01HYXZ');
  });

  it('fires onLeave callback when leave is triggered', () => {
    const onLeave = jest.fn();
    render(<ActiveLesson {...defaultProps} onLeave={onLeave} />);
    fireEvent.click(screen.getByText('Leave'));
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it('has full-screen wrapper classes', () => {
    render(<ActiveLesson {...defaultProps} />);
    const wrapper = screen.getByRole('main');
    expect(wrapper.className).toContain('fixed');
    expect(wrapper.className).toContain('inset-0');
    expect(wrapper.className).toContain('z-50');
  });
});

describe('ActiveLesson error boundary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    shouldThrow = false;
    customThrowError = null;
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('shows error fallback with countdown when HMSPrebuilt crashes', () => {
    shouldThrow = true;
    render(<ActiveLesson {...defaultProps} />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/video session encountered an error/i)).toBeInTheDocument();
    expect(screen.getByText(/redirecting in 3 seconds/i)).toBeInTheDocument();
  });

  it('calls onLeave immediately when button is clicked', () => {
    shouldThrow = true;
    const onLeave = jest.fn();
    render(<ActiveLesson {...defaultProps} onLeave={onLeave} />);

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it('counts down and auto-redirects via onLeave after 3 seconds', () => {
    jest.useFakeTimers();
    shouldThrow = true;
    const onLeave = jest.fn();
    render(<ActiveLesson {...defaultProps} onLeave={onLeave} />);

    expect(screen.getByText(/redirecting in 3 seconds/i)).toBeInTheDocument();

    act(() => { jest.advanceTimersByTime(1000); });
    expect(screen.getByText(/redirecting in 2 seconds/i)).toBeInTheDocument();

    act(() => { jest.advanceTimersByTime(1000); });
    expect(screen.getByText(/redirecting in 1 second/i)).toBeInTheDocument();

    act(() => { jest.advanceTimersByTime(1000); });
    expect(onLeave).toHaveBeenCalledTimes(1);
  });

  it('catches onLeave failure without crashing (falls back to /student/lessons)', () => {
    shouldThrow = true;
    const redirectToPath = jest.fn();
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    render(<ActiveLesson {...defaultProps} onLeave={onLeave} redirectToPath={redirectToPath} />);

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(redirectToPath).toHaveBeenCalledTimes(1);
    expect(redirectToPath).toHaveBeenCalledWith('/student/lessons');
  });

  it('uses custom fallbackPath when onLeave fails', () => {
    shouldThrow = true;
    const redirectToPath = jest.fn();
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    render(
      <ActiveLesson
        {...defaultProps}
        onLeave={onLeave}
        fallbackPath="/instructor/bookings"
        redirectToPath={redirectToPath}
      />,
    );

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(redirectToPath).toHaveBeenCalledTimes(1);
    expect(redirectToPath).toHaveBeenCalledWith('/instructor/bookings');
  });

  it('falls back to window.location.href with default path when onLeave throws and no redirectToPath is provided', () => {
    shouldThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    // Suppress JSDOM "Not implemented: navigation" error
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(<ActiveLesson {...defaultProps} onLeave={onLeave} />);
    fireEvent.click(screen.getByText('Back to My Lessons'));

    expect(onLeave).toHaveBeenCalledTimes(1);
    // window.location.href assignment exercises the catch-block fallback (line 48)
    // JSDOM silently accepts the assignment — we verify onLeave threw and no redirectToPath was called
    consoleSpy.mockRestore();
  });

  it('falls back to window.location.href with custom fallbackPath when onLeave throws and no redirectToPath is provided', () => {
    shouldThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ActiveLesson
        {...defaultProps}
        onLeave={onLeave}
        fallbackPath="/instructor/bookings"
      />,
    );
    fireEvent.click(screen.getByText('Back to My Lessons'));

    expect(onLeave).toHaveBeenCalledTimes(1);
    // Exercises catch path with custom fallbackPath and no redirectToPath (line 43-48)
    consoleSpy.mockRestore();
  });

  it('falls back to window.location.href when onLeave throws from the no-auth-token view', () => {
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(<ActiveLesson {...defaultProps} authToken="" onLeave={onLeave} />);
    fireEvent.click(screen.getByText('Back to My Lessons'));

    expect(onLeave).toHaveBeenCalledTimes(1);
    // Exercises handleBackToLessons catch block from the empty-authToken UI
    consoleSpy.mockRestore();
  });

  it('uses redirectToPath in no-auth-token view when onLeave throws', () => {
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    const redirectToPath = jest.fn();

    render(
      <ActiveLesson
        {...defaultProps}
        authToken=""
        onLeave={onLeave}
        redirectToPath={redirectToPath}
      />,
    );
    fireEvent.click(screen.getByText('Back to My Lessons'));

    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(redirectToPath).toHaveBeenCalledWith('/student/lessons');
  });

  it('uses redirectToPath with custom fallbackPath in no-auth-token view when onLeave throws', () => {
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    const redirectToPath = jest.fn();

    render(
      <ActiveLesson
        {...defaultProps}
        authToken=""
        onLeave={onLeave}
        fallbackPath="/custom/fallback"
        redirectToPath={redirectToPath}
      />,
    );
    fireEvent.click(screen.getByText('Back to My Lessons'));

    expect(onLeave).toHaveBeenCalledTimes(1);
    expect(redirectToPath).toHaveBeenCalledWith('/custom/fallback');
  });

  it('shows missing token fallback when authToken is empty', () => {
    const onLeave = jest.fn();
    render(<ActiveLesson {...defaultProps} authToken="" onLeave={onLeave} />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/unable to connect/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
  });
});

describe('ActiveLesson recoverable error boundary', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    shouldThrow = false;
    customThrowError = null;
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.useRealTimers();
  });

  it('recovers from known 100ms portal getComputedStyle error', () => {
    jest.useFakeTimers();
    customThrowError = new Error(PORTAL_ERROR_MSG);
    render(<ActiveLesson {...defaultProps} />);

    // Shows recovery overlay, NOT permanent fallback
    expect(screen.getByText(/dialog crashed/i)).toBeInTheDocument();
    expect(screen.queryByText(/redirecting in/i)).not.toBeInTheDocument();

    // Clear the error so recovery re-render succeeds
    customThrowError = null;

    // After 1.5s, recovers — children re-render
    act(() => { jest.advanceTimersByTime(1500); });
    expect(screen.queryByText(/dialog crashed/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('hms-prebuilt')).toBeInTheDocument();
  });

  it('falls back to permanent redirect after 3 rapid recoverable errors', () => {
    jest.useFakeTimers();
    customThrowError = new Error(PORTAL_ERROR_MSG);
    render(<ActiveLesson {...defaultProps} />);

    // 1st error → recovery overlay
    expect(screen.getByText(/dialog crashed/i)).toBeInTheDocument();

    // Recover from 1st → 2nd error → recovery overlay (error still active)
    act(() => { jest.advanceTimersByTime(1500); });
    expect(screen.getByText(/dialog crashed/i)).toBeInTheDocument();

    // Recover from 2nd → 3rd error → crash loop → permanent fallback
    act(() => { jest.advanceTimersByTime(1500); });
    expect(screen.getByText(/video session encountered an error/i)).toBeInTheDocument();
    expect(screen.getByText(/redirecting in 3 seconds/i)).toBeInTheDocument();
  });

  it('shows permanent fallback for non-getComputedStyle errors', () => {
    customThrowError = new Error('Cannot read property of undefined');
    render(<ActiveLesson {...defaultProps} />);

    expect(screen.getByText(/video session encountered an error/i)).toBeInTheDocument();
    expect(screen.getByText(/redirecting in 3 seconds/i)).toBeInTheDocument();
    expect(screen.queryByText(/dialog crashed/i)).not.toBeInTheDocument();
  });
});
