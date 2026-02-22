import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PauseAccountModal from '../PauseAccountModal';
import { fetchWithAuth } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;

const renderModal = (props?: { onClose?: jest.Mock; onPaused?: jest.Mock }) => {
  const onClose = props?.onClose ?? jest.fn();
  const onPaused = props?.onPaused ?? jest.fn();
  render(<PauseAccountModal onClose={onClose} onPaused={onPaused} />);
  return { onClose, onPaused };
};

describe('PauseAccountModal', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('renders content and handles cancel', async () => {
    const { onClose } = renderModal();

    expect(screen.getByText('Pause account')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onPaused on successful pause', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true });
    const { onPaused } = renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => expect(onPaused).toHaveBeenCalled());
  });

  it('shows conflict error details for 409', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: jest.fn().mockResolvedValue({ detail: 'Future bookings exist' }),
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => {
      expect(screen.getByText('Future bookings exist')).toBeInTheDocument();
    });
  });

  it('shows a generic error for non-409 failures', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({ ok: false, status: 500, json: jest.fn() });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to pause account. Please try again.')).toBeInTheDocument();
    });
  });

  it('shows a network error on request failure', async () => {
    fetchWithAuthMock.mockRejectedValueOnce(new Error('Network down'));

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => {
      expect(screen.getByText('Network error.')).toBeInTheDocument();
    });
  });

  it('shows fallback 409 message when res.json() throws', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: jest.fn().mockRejectedValue(new Error('invalid json')),
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => {
      // extractApiErrorMessage({}, fallback) should return the fallback
      expect(
        screen.getByText('Cannot pause while future bookings exist.')
      ).toBeInTheDocument();
    });
  });

  it('disables buttons and shows loading text while pausing', async () => {
    let resolveRequest: (value: { ok: boolean }) => void;
    fetchWithAuthMock.mockReturnValueOnce(
      new Promise<{ ok: boolean }>((resolve) => {
        resolveRequest = resolve;
      })
    );

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    // While loading: button text changes, both buttons disabled
    await waitFor(() => {
      expect(screen.getByText('Pausing\u2026')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Pausing\u2026' })).toBeDisabled();

    // Resolve the request
    resolveRequest!({ ok: true });

    await waitFor(() => {
      expect(screen.queryByText('Pausing\u2026')).not.toBeInTheDocument();
    });
  });

  it('does not call onPaused on error responses', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: jest.fn(),
    });

    const { onPaused } = renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to pause account. Please try again.')).toBeInTheDocument();
    });

    expect(onPaused).not.toHaveBeenCalled();
  });

  it('clears previous error on retry', async () => {
    // First attempt: 500 error
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: jest.fn(),
    });

    const { onPaused } = renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to pause account. Please try again.')).toBeInTheDocument();
    });

    // Second attempt: success
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true });

    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));

    await waitFor(() => {
      expect(onPaused).toHaveBeenCalled();
    });

    // Error should be cleared
    expect(screen.queryByText('Failed to pause account. Please try again.')).not.toBeInTheDocument();
  });
});
