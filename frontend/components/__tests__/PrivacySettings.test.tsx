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
});
