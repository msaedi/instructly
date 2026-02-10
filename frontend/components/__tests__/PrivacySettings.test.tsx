import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PrivacySettings } from '../PrivacySettings';
import { setUserPreference } from '@/lib/searchTracking';
import { logger } from '@/lib/logger';

jest.mock('@/lib/searchTracking', () => ({
  setUserPreference: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: { info: jest.fn() },
}));

describe('PrivacySettings', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders heading and description', () => {
    render(<PrivacySettings />);

    expect(screen.getByText(/Privacy Settings/i)).toBeInTheDocument();
    expect(screen.getByText(/guest sessions/i)).toBeInTheDocument();
  });

  it('toggles the clear-on-logout preference', async () => {
    const user = userEvent.setup();
    render(<PrivacySettings />);

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();

    await user.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(setUserPreference).toHaveBeenCalledWith('clearDataOnLogout', true);
    expect(logger.info).toHaveBeenCalledWith('Privacy setting updated', { clearDataOnLogout: true });
  });

  it('supports className injection', () => {
    const { container } = render(<PrivacySettings className="custom-class" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('allows disabling the preference', async () => {
    const user = userEvent.setup();
    render(<PrivacySettings />);

    const checkbox = screen.getByRole('checkbox');
    await user.click(checkbox);
    await user.click(checkbox);

    expect(setUserPreference).toHaveBeenCalledWith('clearDataOnLogout', false);
  });

  it('keeps the help text visible', () => {
    render(<PrivacySettings />);

    expect(screen.getByText(/clear search history when i log out/i)).toBeInTheDocument();
    expect(screen.getByText(/expire after 30 days/i)).toBeInTheDocument();
  });

  it('does not render loading skeleton (isLoading is always false)', () => {
    const { container } = render(<PrivacySettings />);

    // The skeleton has animate-pulse class which should never render
    const skeleton = container.querySelector('.animate-pulse');
    expect(skeleton).not.toBeInTheDocument();

    // The main heading should be present since we are in the loaded state
    expect(screen.getByText('Privacy Settings')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).toBeInTheDocument();
  });

  it('applies default empty className when none provided', () => {
    const { container } = render(<PrivacySettings />);

    const root = container.firstChild as HTMLElement;
    expect(root).toHaveClass('privacy-settings');
  });

  it('calls setUserPreference and logger.info with false when unchecked', async () => {
    const user = userEvent.setup();
    render(<PrivacySettings />);

    const checkbox = screen.getByRole('checkbox');
    // Toggle on, then off
    await user.click(checkbox);
    await user.click(checkbox);

    // Second call should be with false
    expect(setUserPreference).toHaveBeenLastCalledWith('clearDataOnLogout', false);
    expect(logger.info).toHaveBeenLastCalledWith('Privacy setting updated', { clearDataOnLogout: false });
  });
});
