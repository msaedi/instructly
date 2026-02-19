import { render, screen, fireEvent, act } from '@testing-library/react';

let shouldThrow = false;

jest.mock('@100mslive/roomkit-react', () => ({
  HMSPrebuilt: (props: Record<string, unknown>) => {
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

describe('ActiveLesson', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    shouldThrow = false;
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

  it('catches onLeave failure without crashing (falls back to hard redirect)', () => {
    shouldThrow = true;
    const onLeave = jest.fn().mockImplementation(() => {
      throw new Error('Navigation failed');
    });
    render(<ActiveLesson {...defaultProps} onLeave={onLeave} />);

    // Click should not throw — _safeLeave catches and falls back to
    // window.location.href = '/lessons' (not interceptable in jsdom)
    fireEvent.click(screen.getByText('Back to My Lessons'));
    expect(onLeave).toHaveBeenCalledTimes(1);
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
