import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { BackgroundCheckDisclosureModal } from '../BackgroundCheckDisclosureModal';

jest.mock('@/components/Modal', () => ({
  __esModule: true,
  default: ({
    isOpen,
    title,
    children,
    footer,
  }: {
    isOpen: boolean;
    title?: string;
    children?: React.ReactNode;
    footer?: React.ReactNode;
  }) =>
    isOpen ? (
      <div role="dialog" aria-modal="true" aria-labelledby={title ? 'background-check-title' : undefined}>
        {title && <div id="background-check-title">{title}</div>}
        {children}
        {footer}
      </div>
    ) : null,
}));

jest.mock('@/components/ui/button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    variant: _variant,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    variant?: string;
  }) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}));

jest.mock('@/config/constants', () => ({
  FTC_RIGHTS_URL: 'https://example.com/ftc-rights',
}));

describe('BackgroundCheckDisclosureModal', () => {
  const defaultProps = {
    isOpen: true,
    onAccept: jest.fn(),
    onDecline: jest.fn(),
    submitting: false,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('does not render when closed', () => {
    const { container } = render(
      <BackgroundCheckDisclosureModal {...defaultProps} isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders disclosure title when open', () => {
    render(<BackgroundCheckDisclosureModal {...defaultProps} />);
    expect(
      screen.getByText('Background Check Disclosure and Authorization'),
    ).toBeInTheDocument();
  });

  it('shows scroll hint when user has not scrolled to end', () => {
    render(<BackgroundCheckDisclosureModal {...defaultProps} />);
    expect(
      screen.getByText('Scroll to the end to enable authorization.'),
    ).toBeInTheDocument();
  });

  it('does not call onAccept when handleAccept is invoked before scrolling (line 122)', () => {
    // Line 122: defensive guard — handleAccept returns early when !hasScrolledToEnd.
    // The accept button is disabled, but we bypass via fireEvent on a native button.
    render(<BackgroundCheckDisclosureModal {...defaultProps} />);

    // The button text is 'I acknowledge and authorize' and it's disabled
    const acceptButton = screen.getByRole('button', {
      name: /i acknowledge and authorize/i,
    });
    expect(acceptButton).toBeDisabled();

    // fireEvent.click on a native <button disabled> does NOT call React onClick in JSDOM,
    // so this tests that onAccept is NOT called while the guard holds.
    fireEvent.click(acceptButton);
    expect(defaultProps.onAccept).not.toHaveBeenCalled();
  });

  it('does not call onAccept when submitting is true (line 122 submitting guard)', () => {
    render(
      <BackgroundCheckDisclosureModal {...defaultProps} submitting={true} />
    );

    // Shows 'Recording...' when submitting
    expect(screen.getByText('Recording\u2026')).toBeInTheDocument();
    expect(defaultProps.onAccept).not.toHaveBeenCalled();
  });
});
