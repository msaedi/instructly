import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CalendarSettingsSection from '../CalendarSettingsSection';

describe('CalendarSettingsSection', () => {
  const baseProps = {
    value: {
      nonTravelBufferMinutes: 15,
      travelBufferMinutes: 60,
      overnightProtectionEnabled: true,
    },
    onNonTravelChange: jest.fn(),
    onTravelChange: jest.fn(),
    onOvernightProtectionChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders without the protections link when no reopen handler is provided', () => {
    render(<CalendarSettingsSection {...baseProps} saveState="idle" />);

    expect(screen.queryByRole('button', { name: 'About calendar protections' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('calendar-settings-save-state')).not.toBeInTheDocument();
  });

  it('shows saving and saved states and opens the protections info link', async () => {
    const user = userEvent.setup();
    const onOpenCalendarProtectionsInfo = jest.fn();

    const { rerender } = render(
      <CalendarSettingsSection
        {...baseProps}
        saveState="saving"
        onOpenCalendarProtectionsInfo={onOpenCalendarProtectionsInfo}
      />
    );

    expect(screen.getByTestId('calendar-settings-save-state')).toHaveTextContent('Saving…');

    rerender(
      <CalendarSettingsSection
        {...baseProps}
        saveState="saved"
        onOpenCalendarProtectionsInfo={onOpenCalendarProtectionsInfo}
      />
    );

    expect(screen.getByTestId('calendar-settings-save-state')).toHaveTextContent('Saved');

    await user.click(screen.getByRole('button', { name: 'About calendar protections' }));

    expect(onOpenCalendarProtectionsInfo).toHaveBeenCalledTimes(1);
  });
});
