import { render, screen } from '@testing-library/react';
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

  it('renders buffer cards and overnight protection', () => {
    render(<CalendarSettingsSection {...baseProps} saveState="idle" />);

    expect(screen.getByText('Staying put')).toBeInTheDocument();
    expect(screen.getByText('Traveling to student')).toBeInTheDocument();
    expect(screen.getByText('Overnight booking protection')).toBeInTheDocument();
    expect(screen.queryByTestId('calendar-settings-save-state')).not.toBeInTheDocument();
  });

  it('shows saving and saved states', () => {
    const { rerender } = render(
      <CalendarSettingsSection
        {...baseProps}
        saveState="saving"
      />
    );

    expect(screen.getByTestId('calendar-settings-save-state')).toHaveTextContent('Saving…');

    rerender(
      <CalendarSettingsSection
        {...baseProps}
        saveState="saved"
      />
    );

    expect(screen.getByTestId('calendar-settings-save-state')).toHaveTextContent('Saved');
  });
});
