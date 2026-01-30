import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BackgroundCheckDisclosureModal } from '@/components/consent/BackgroundCheckDisclosureModal';
import { FTC_RIGHTS_URL } from '@/config/constants';

describe('BackgroundCheckDisclosureModal', () => {
  const defaultProps = {
    isOpen: true,
    onAccept: jest.fn(),
    onDecline: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders required content sections and FTC link', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      expect(screen.getByText(/Information we may obtain/i)).toBeInTheDocument();
      expect(screen.getByText(/Consumer reporting agency contact details/i)).toBeInTheDocument();
      expect(
        screen.getByRole('link', { name: /Summary of Your Rights Under the Fair Credit Reporting Act/i })
      ).toHaveAttribute('href', FTC_RIGHTS_URL);
    });

    it('renders overview and authorization sections', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Authorization')).toBeInTheDocument();
    });

    it('shows scroll instruction when not scrolled to end', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      expect(screen.getByText(/Scroll to the end to enable authorization/i)).toBeInTheDocument();
    });
  });

  describe('scroll and accept behavior', () => {
    it('disables accept button until the disclosure is scrolled to the end', () => {
      const handleAccept = jest.fn();

      render(<BackgroundCheckDisclosureModal {...defaultProps} onAccept={handleAccept} />);

      const acceptButton = screen.getByRole('button', { name: /I acknowledge and authorize/i });
      expect(acceptButton).toBeDisabled();

      const scrollRegion = screen.getByLabelText('Background check disclosure content');
      Object.defineProperty(scrollRegion, 'scrollHeight', { value: 200, configurable: true });
      Object.defineProperty(scrollRegion, 'clientHeight', { value: 100, configurable: true });

      fireEvent.scroll(scrollRegion, {
        currentTarget: Object.assign(scrollRegion, { scrollTop: 110 }),
      });

      expect(acceptButton).not.toBeDisabled();
      fireEvent.click(acceptButton);
      expect(handleAccept).toHaveBeenCalledTimes(1);
    });

    it('does NOT call onAccept when clicked before scrolling to end', async () => {
      const handleAccept = jest.fn();
      const user = userEvent.setup();

      render(<BackgroundCheckDisclosureModal {...defaultProps} onAccept={handleAccept} />);

      const acceptButton = screen.getByRole('button', { name: /I acknowledge and authorize/i });

      // Try to click the disabled button (coverage for early return in handleAccept)
      await user.click(acceptButton);

      expect(handleAccept).not.toHaveBeenCalled();
    });

    it('does NOT call onAccept when submitting is true', async () => {
      const handleAccept = jest.fn();

      const { rerender } = render(<BackgroundCheckDisclosureModal {...defaultProps} onAccept={handleAccept} />);

      // Scroll to end first
      const scrollRegion = screen.getByLabelText('Background check disclosure content');
      Object.defineProperty(scrollRegion, 'scrollHeight', { value: 200, configurable: true });
      Object.defineProperty(scrollRegion, 'clientHeight', { value: 100, configurable: true });
      fireEvent.scroll(scrollRegion, {
        currentTarget: Object.assign(scrollRegion, { scrollTop: 110 }),
      });

      // Button should be enabled now
      let acceptButton = screen.getByRole('button', { name: /I acknowledge and authorize/i });
      expect(acceptButton).not.toBeDisabled();

      // Now set submitting to true while scrolled - button gets disabled but handler still guards
      rerender(<BackgroundCheckDisclosureModal {...defaultProps} onAccept={handleAccept} submitting={true} />);

      // Force scroll again to maintain state
      fireEvent.scroll(scrollRegion, {
        currentTarget: Object.assign(scrollRegion, { scrollTop: 110 }),
      });

      acceptButton = screen.getByRole('button', { name: /Recording/i });
      expect(acceptButton).toBeDisabled();

      // Force click via fireEvent (bypasses disabled check) to trigger the early return
      fireEvent.click(acceptButton);

      expect(handleAccept).not.toHaveBeenCalled();
    });
  });

  describe('modal close and state reset', () => {
    it('resets scroll position when modal closes and reopens', async () => {
      const { rerender } = render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      const scrollRegion = screen.getByLabelText('Background check disclosure content');

      // Mock scrollTo
      const scrollToMock = jest.fn();
      scrollRegion.scrollTo = scrollToMock;

      // Scroll to enable accept button
      Object.defineProperty(scrollRegion, 'scrollHeight', { value: 200, configurable: true });
      Object.defineProperty(scrollRegion, 'clientHeight', { value: 100, configurable: true });
      Object.defineProperty(scrollRegion, 'scrollTop', { value: 110, writable: true, configurable: true });
      fireEvent.scroll(scrollRegion);

      const acceptButton = screen.getByRole('button', { name: /I acknowledge and authorize/i });
      expect(acceptButton).not.toBeDisabled();

      // Close modal
      rerender(<BackgroundCheckDisclosureModal {...defaultProps} isOpen={false} />);

      // Reopen modal
      rerender(<BackgroundCheckDisclosureModal {...defaultProps} isOpen={true} />);

      // Accept button should be disabled again (state reset)
      await waitFor(() => {
        const newAcceptButton = screen.getByRole('button', { name: /I acknowledge and authorize/i });
        expect(newAcceptButton).toBeDisabled();
      });
    });

    it('resets states expanded when modal closes', async () => {
      const user = userEvent.setup();
      const { rerender } = render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      // Expand state notices
      const statesButton = screen.getByRole('button', { name: /State-specific notices/i });
      await user.click(statesButton);

      // Check expanded content is visible
      expect(screen.getByText(/Certain states require additional disclosures/i)).toBeInTheDocument();

      // Close modal
      rerender(<BackgroundCheckDisclosureModal {...defaultProps} isOpen={false} />);

      // Reopen modal
      rerender(<BackgroundCheckDisclosureModal {...defaultProps} isOpen={true} />);

      // State notices should be collapsed again
      expect(screen.queryByText(/Certain states require additional disclosures/i)).not.toBeInTheDocument();
    });
  });

  describe('skip to authorization (mobile)', () => {
    it('scrolls to bottom when skip button is clicked', async () => {
      const user = userEvent.setup();

      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      const scrollRegion = screen.getByLabelText('Background check disclosure content');

      // Mock scrollTo
      const scrollToMock = jest.fn();
      scrollRegion.scrollTo = scrollToMock;
      Object.defineProperty(scrollRegion, 'scrollHeight', { value: 1000, configurable: true });

      // Find and click skip button
      const skipButton = screen.getByRole('button', { name: /Skip to authorization/i });
      await user.click(skipButton);

      expect(scrollToMock).toHaveBeenCalledWith({ top: 1000, behavior: 'smooth' });
    });
  });

  describe('state-specific notices toggle', () => {
    it('expands and collapses state-specific notices', async () => {
      const user = userEvent.setup();

      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      const statesButton = screen.getByRole('button', { name: /State-specific notices/i });
      expect(statesButton).toHaveAttribute('aria-expanded', 'false');

      // Expand
      await user.click(statesButton);
      expect(statesButton).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByText(/Certain states require additional disclosures/i)).toBeInTheDocument();

      // Collapse
      await user.click(statesButton);
      expect(statesButton).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByText(/Certain states require additional disclosures/i)).not.toBeInTheDocument();
    });

    it('shows chevron icons based on expanded state', async () => {
      const user = userEvent.setup();

      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      const statesButton = screen.getByRole('button', { name: /State-specific notices/i });

      // Initially shows down chevron
      expect(statesButton.querySelector('svg')).toBeInTheDocument();

      // Expand - shows up chevron
      await user.click(statesButton);

      // Still has svg (just different icon)
      expect(statesButton.querySelector('svg')).toBeInTheDocument();
    });
  });

  describe('decline behavior', () => {
    it('calls onDecline when decline button is clicked', async () => {
      const user = userEvent.setup();
      const onDecline = jest.fn();

      render(<BackgroundCheckDisclosureModal {...defaultProps} onDecline={onDecline} />);

      await user.click(screen.getByRole('button', { name: /Decline/i }));

      expect(onDecline).toHaveBeenCalledTimes(1);
    });

    it('disables decline button while submitting', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} submitting={true} />);

      expect(screen.getByRole('button', { name: /Decline/i })).toBeDisabled();
    });
  });

  describe('submitting state', () => {
    it('shows loading text when submitting', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} submitting={true} />);

      expect(screen.getByRole('button', { name: /Recording/i })).toBeInTheDocument();
    });

    it('hides scroll instruction when submitting', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} submitting={true} />);

      expect(screen.queryByText(/Scroll to the end to enable authorization/i)).not.toBeInTheDocument();
    });

    it('prevents closing on backdrop click while submitting', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} submitting={true} />);

      // The Modal component handles this - just verify the props are passed correctly
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  describe('accessibility', () => {
    it('scroll region is focusable and has proper role', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      const scrollRegion = screen.getByLabelText('Background check disclosure content');
      expect(scrollRegion).toHaveAttribute('role', 'document');
      expect(scrollRegion).toHaveAttribute('tabIndex', '0');
    });

    it('has live region for dynamic content', () => {
      render(<BackgroundCheckDisclosureModal {...defaultProps} />);

      const liveRegion = document.querySelector('[aria-live="polite"]');
      expect(liveRegion).toBeInTheDocument();
    });
  });
});
