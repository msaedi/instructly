import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChangePasswordModal from '../ChangePasswordModal';
import { fetchWithAuth } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;

const renderModal = (props?: { onClose?: jest.Mock }) => {
  const onClose = props?.onClose ?? jest.fn();
  render(<ChangePasswordModal onClose={onClose} />);
  return { onClose };
};
const getPasswordInputs = (): [HTMLInputElement, HTMLInputElement, HTMLInputElement] => {
  return [
    screen.getByLabelText('Current password') as HTMLInputElement,
    screen.getByLabelText('New password') as HTMLInputElement,
    screen.getByLabelText('Confirm new password') as HTMLInputElement,
  ];
};

describe('ChangePasswordModal', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it('disables submit when inputs are invalid', () => {
    renderModal();

    const saveButton = screen.getByRole('button', { name: 'Save password' });
    expect(saveButton).toBeDisabled();
  });

  it('associates labels with matching password input ids', () => {
    renderModal();

    expect(screen.getByLabelText('Current password')).toHaveAttribute('id', 'current-password');
    expect(screen.getByLabelText('New password')).toHaveAttribute('id', 'new-password');
    expect(screen.getByLabelText('Confirm new password')).toHaveAttribute('id', 'confirm-password');
  });

  it('renders with dialog semantics wired to the heading', () => {
    renderModal();

    const dialog = screen.getByRole('dialog', { name: /change password/i });
    const heading = screen.getByRole('heading', { name: /change password/i });

    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', heading.getAttribute('id'));
  });

  it('traps focus inside the dialog when tabbing', () => {
    renderModal();

    const firstInput = screen.getByLabelText('Current password');
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
            Open change password
          </button>
          {open ? <ChangePasswordModal onClose={() => setOpen(false)} /> : null}
        </div>
      );
    }

    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Open change password' });
    await user.click(opener);

    expect(screen.getByRole('dialog', { name: /change password/i })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /change password/i })).not.toBeInTheDocument();
    });
    expect(opener).toHaveFocus();
  });

  it('calls onClose when cancel is clicked', async () => {
    const { onClose } = renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onClose).toHaveBeenCalled();
  });

  it('submits a valid password change', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true });
    const { onClose } = renderModal();

    const [currentInput, newInput, confirmInput] = getPasswordInputs();
    await userEvent.type(currentInput, 'current123');
    await userEvent.type(newInput, 'newpassword');
    await userEvent.type(confirmInput, 'newpassword');

    await userEvent.click(screen.getByRole('button', { name: 'Save password' }));

    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalled());
    expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: 'current123', new_password: 'newpassword' }),
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('shows error when API responds with failure', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockResolvedValue({ detail: 'Invalid password' }),
    });

    renderModal();

    const [currentInput, newInput, confirmInput] = getPasswordInputs();
    await userEvent.type(currentInput, 'current123');
    await userEvent.type(newInput, 'newpassword');
    await userEvent.type(confirmInput, 'newpassword');

    await userEvent.click(screen.getByRole('button', { name: 'Save password' }));

    await waitFor(() => {
      expect(screen.getByText('Invalid password')).toBeInTheDocument();
    });
  });

  it('shows network error on request failure', async () => {
    fetchWithAuthMock.mockRejectedValueOnce(new Error('Network down'));

    renderModal();

    const [currentInput, newInput, confirmInput] = getPasswordInputs();
    await userEvent.type(currentInput, 'current123');
    await userEvent.type(newInput, 'newpassword');
    await userEvent.type(confirmInput, 'newpassword');

    await userEvent.click(screen.getByRole('button', { name: 'Save password' }));

    await waitFor(() => {
      expect(screen.getByText('Network error.')).toBeInTheDocument();
    });
  });

  it('handles JSON parse failure gracefully', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockRejectedValue(new Error('Invalid JSON')),
    });

    renderModal();

    const [currentInput, newInput, confirmInput] = getPasswordInputs();
    await userEvent.type(currentInput, 'current123');
    await userEvent.type(newInput, 'newpassword');
    await userEvent.type(confirmInput, 'newpassword');

    await userEvent.click(screen.getByRole('button', { name: 'Save password' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to change password.')).toBeInTheDocument();
    });
  });

  it('does not submit when canSubmit is false', async () => {
    renderModal();

    // Current password too short (needs 6 chars)
    const [currentInput, newInput, confirmInput] = getPasswordInputs();
    await userEvent.type(currentInput, '12345');  // Only 5 chars
    await userEvent.type(newInput, 'newpassword');
    await userEvent.type(confirmInput, 'newpassword');

    // Button should be disabled
    expect(screen.getByRole('button', { name: 'Save password' })).toBeDisabled();
    expect(fetchWithAuthMock).not.toHaveBeenCalled();
  });
});
