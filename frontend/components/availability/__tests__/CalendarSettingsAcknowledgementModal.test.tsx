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

  it('renders the re-opened info mode as a closable auto-height modal', async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();

    render(
      <CalendarSettingsAcknowledgementModal
        isOpen={true}
        variant="mixed_formats"
        mode="info"
        onClose={onClose}
      />
    );

    const modalShell = document.querySelector('.max-w-md');
    const backdrop = document.querySelector('.insta-dialog-backdrop');

    expect(modalShell?.className).toContain('h-auto');
    expect(backdrop?.className).toContain('backdrop-blur-sm');
    expect(backdrop?.className).toContain('bg-black/50');

    await user.click(screen.getByRole('button', { name: 'Close' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('falls back to the modal close handler when info mode is rendered without an explicit onClose', async () => {
    const user = userEvent.setup();

    render(
      <CalendarSettingsAcknowledgementModal
        isOpen={true}
        variant="non_travel_only"
        mode="info"
      />
    );

    await user.click(screen.getByLabelText('Close modal'));

    expect(screen.getByTestId('calendar-settings-acknowledgement-modal')).toBeInTheDocument();
  });
});
