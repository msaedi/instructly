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
});
