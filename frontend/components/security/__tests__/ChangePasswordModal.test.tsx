import { render, screen, waitFor } from '@testing-library/react';
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
  const labels = ['Current password', 'New password', 'Confirm new password'];
  const inputs = labels.map((labelText) => {
    const label = screen.getByText(labelText);
    const input = label.parentElement?.querySelector('input');
    if (!input) {
      throw new Error(`Missing input for ${labelText}`);
    }
    return input as HTMLInputElement;
  });
  return inputs as [HTMLInputElement, HTMLInputElement, HTMLInputElement];
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
