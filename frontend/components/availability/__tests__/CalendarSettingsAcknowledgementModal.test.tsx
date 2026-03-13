import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CalendarSettingsAcknowledgementModal from '../CalendarSettingsAcknowledgementModal';

describe('CalendarSettingsAcknowledgementModal', () => {
  it('renders mixed-format copy', () => {
    render(
      <CalendarSettingsAcknowledgementModal
        isOpen={true}
        variant="mixed_formats"
        onAcknowledge={jest.fn()}
      />
    );

    expect(
      screen.getByText(/15 minutes between lessons when you're staying put/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/60 minutes when you need to travel to a student's location/i)
    ).toBeInTheDocument();
  });

  it('renders non-travel-only copy', () => {
    render(
      <CalendarSettingsAcknowledgementModal
        isOpen={true}
        variant="non_travel_only"
        onAcknowledge={jest.fn()}
      />
    );

    expect(
      screen.getByText(/We automatically add 15 minutes of buffer time between your lessons/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Students can book up to 1 hour before your lessons/i)).toBeInTheDocument();
  });

  it('renders travel-only copy and calls acknowledge', async () => {
    const user = userEvent.setup();
    const onAcknowledge = jest.fn();

    render(
      <CalendarSettingsAcknowledgementModal
        isOpen={true}
        variant="travel_only"
        onAcknowledge={onAcknowledge}
      />
    );

    expect(
      screen.getByText(/We automatically add 60 minutes of buffer time between your lessons/i)
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'OK' }));

    expect(onAcknowledge).toHaveBeenCalledTimes(1);
  });

  it('shows the submitting state', () => {
    render(
      <CalendarSettingsAcknowledgementModal
        isOpen={true}
        variant="non_travel_only"
        isSubmitting={true}
        onAcknowledge={jest.fn()}
      />
    );

    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
  });
});
