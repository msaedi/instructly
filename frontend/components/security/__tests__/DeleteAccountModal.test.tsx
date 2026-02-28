import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

    const passwordInput = screen.getByLabelText('Password') as HTMLInputElement;
    expect(passwordInput.type).toBe('password');

    await userEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(passwordInput.type).toBe('text');

    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(passwordInput.type).toBe('password');
  });

  it('shows error when password verification fails', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: false });
    renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Incorrect password.');
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

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Cannot delete');
    });
  });

  it('calls onDeleted on success', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: true });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true });
    const { onDeleted } = renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
  });

  it('calls onClose when cancel is clicked', async () => {
    const { onClose } = renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onClose).toHaveBeenCalled();
  });

  it('shows generic error when deletion fails with non-400 status', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: true });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: jest.fn().mockResolvedValue({ message: 'Internal server error' }),
    });

    renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Failed to delete account. Please try again later.');
    });
  });

  it('shows generic error when deletion response json parsing fails', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: true });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: jest.fn().mockRejectedValue(new Error('Invalid JSON')),
    });

    renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Failed to delete account. Please try again later.');
    });
  });

  it('shows unexpected error when entire submission throws', async () => {
    fetchApiMock.mockRejectedValueOnce(new Error('Network failure'));

    renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Unexpected error. Please try again.');
    });
  });

  it('enables submit button when DELETE typed in different case and password >= 6 chars', async () => {
    renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'delete');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    const deleteButton = screen.getByRole('button', { name: 'Delete My Account' });
    expect(deleteButton).not.toBeDisabled();
  });

  it('keeps submit disabled when password is shorter than 6 characters', async () => {
    renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), '12345');

    const deleteButton = screen.getByRole('button', { name: 'Delete My Account' });
    expect(deleteButton).toBeDisabled();
  });

  it('shows generic error when deletion fails with 400 but no detail field', async () => {
    fetchApiMock.mockResolvedValueOnce({ ok: true });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: jest.fn().mockResolvedValue({}),
    });

    renderModal();

    await userEvent.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE');
    await userEvent.type(screen.getByLabelText('Password'), 'password');

    await userEvent.click(screen.getByRole('button', { name: 'Delete My Account' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Failed to delete account. Please try again later.');
    });
  });

  it('renders with dialog semantics wired to the heading', () => {
    renderModal();

    const dialog = screen.getByRole('dialog', { name: /delete account/i });
    const heading = screen.getByRole('heading', { name: /delete account/i });

    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', heading.getAttribute('id'));
  });

  it('traps focus inside the dialog when tabbing', () => {
    renderModal();

    const firstInput = screen.getByLabelText('Type DELETE to confirm');
    const cancelButton = screen.getByRole('button', { name: 'Cancel' });

    cancelButton.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(firstInput).toHaveFocus();

    firstInput.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(cancelButton).toHaveFocus();
  });

  it('closes on Escape and restores focus to the opener', async () => {
    const user = userEvent.setup();

    function Harness() {
      const [open, setOpen] = React.useState(false);
      return (
        <div>
          <button type="button" onClick={() => setOpen(true)}>
            Open delete account
          </button>
          {open ? (
            <DeleteAccountModal
              email="user@example.com"
              onClose={() => setOpen(false)}
              onDeleted={jest.fn()}
            />
          ) : null}
        </div>
      );
    }

    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Open delete account' });
    await user.click(opener);

    expect(screen.getByRole('dialog', { name: /delete account/i })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /delete account/i })).not.toBeInTheDocument();
    });
    expect(opener).toHaveFocus();
  });
});
