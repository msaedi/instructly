import { render, screen, fireEvent } from '@testing-library/react';

jest.mock('@100mslive/roomkit-react', () => ({
  HMSPrebuilt: (props: Record<string, unknown>) => {
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
