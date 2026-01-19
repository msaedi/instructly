import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeleteAccountModal from '../DeleteAccountModal';
import { fetchAPI, fetchWithAuth } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchAPI: jest.fn(),
  fetchWithAuth: jest.fn(),
}));

const fetchApiMock = fetchAPI as jest.Mock;
const fetchWithAuthMock = fetchWithAuth as jest.Mock;

const renderModal = (props?: { onClose?: jest.Mock; onDeleted?: jest.Mock }) => {
  const onClose = props?.onClose ?? jest.fn();
  const onDeleted = props?.onDeleted ?? jest.fn();
  render(
    <DeleteAccountModal
      email="user@example.com"
      onClose={onClose}
      onDeleted={onDeleted}
    />
  );
  return { onClose, onDeleted };
};

describe('DeleteAccountModal', () => {
  beforeEach(() => {
    fetchApiMock.mockReset();
    fetchWithAuthMock.mockReset();
  });

  it('disables submit until confirmation and password are valid', () => {
    renderModal();

    const deleteButton = screen.getByRole('button', { name: 'Delete My Account' });
    expect(deleteButton).toBeDisabled();
  });

  it('toggles password visibility', async () => {
    renderModal();

    const passwordInput = screen.getByPlaceholderText('Password') as HTMLInputElement;
    expect(passwordInput.type).toBe('password');

    await userEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(passwordInput.type).toBe('text');

    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(passwordInput.type).toBe('password');
  });

  it('shows error when password verification fails', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: false });
    renderModal();

    await userEvent.type(screen.getByPlaceholderText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByText('Incorrect password.')).toBeInTheDocument();
    });
  });

  it('shows error when deletion fails', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: true });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: jest.fn().mockResolvedValue({ detail: 'Cannot delete' }),
    });

    renderModal();

    await userEvent.type(screen.getByPlaceholderText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByText('Cannot delete')).toBeInTheDocument();
    });
  });

  it('calls onDeleted on success', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: true });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true });
    const { onDeleted } = renderModal();

    await userEvent.type(screen.getByPlaceholderText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByPlaceholderText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
  });

  it('calls onClose when cancel is clicked', async () => {
    const { onClose } = renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onClose).toHaveBeenCalled();
  });
});
