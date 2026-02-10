import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TfaModal from '../TfaModal';
import { fetchWithAuth } from '@/lib/api';
import { useTfaStatus } from '@/hooks/queries/useTfaStatus';
import { toast } from 'sonner';

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

jest.mock('@/hooks/queries/useTfaStatus', () => ({
  useTfaStatus: jest.fn(),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;
const useTfaStatusMock = useTfaStatus as jest.Mock;

const renderModal = (props?: { onClose?: jest.Mock; onChanged?: jest.Mock }) => {
  const onClose = props?.onClose ?? jest.fn();
  const onChanged = props?.onChanged ?? jest.fn();
  render(<TfaModal onClose={onClose} onChanged={onChanged} />);
  return { onClose, onChanged };
};

describe('TfaModal', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    useTfaStatusMock.mockReset();
    (toast.success as jest.Mock).mockClear();
  });

  it('initiates setup and renders QR data when 2FA is disabled', async () => {
    useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
    });

    renderModal();

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/2fa/setup/initiate', { method: 'POST' });
    });

    expect(await screen.findByText('Secret (manual entry):')).toBeInTheDocument();
  });

  it('shows error when initiation fails', async () => {
    useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: false, json: jest.fn() });

    renderModal();

    await waitFor(() => {
      expect(screen.getByText('Failed to initiate 2FA.')).toBeInTheDocument();
    });
  });

  it('shows error on verify failure', async () => {
    useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
    fetchWithAuthMock
      .mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: jest.fn().mockResolvedValue({ detail: 'Invalid code' }),
      });

    renderModal();

    const codeInput = await screen.findByPlaceholderText('123 456');
    await userEvent.type(codeInput, '123456');
    await userEvent.click(screen.getByRole('button', { name: 'Verify & Enable' }));

    await waitFor(() => {
      expect(screen.getByText('Invalid code')).toBeInTheDocument();
    });
  });

  it('verifies successfully and allows copy/regenerate', async () => {
    useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
    fetchWithAuthMock
      .mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ backup_codes: ['code1', 'code2'] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ backup_codes: ['code3'] }),
      });

    Object.assign(navigator, {
      clipboard: {
        writeText: jest.fn().mockResolvedValue(undefined),
      },
    });

    const { onChanged } = renderModal();

    const codeInput = await screen.findByPlaceholderText('123 456');
    await userEvent.type(codeInput, '123456');
    await userEvent.click(screen.getByRole('button', { name: 'Verify & Enable' }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('Two‑factor authentication enabled');

    await userEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('code1\ncode2');

    await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }));
    await waitFor(() => {
      expect(screen.getByText('code3')).toBeInTheDocument();
    });
  });

  it('disables 2FA when already enabled', async () => {
    useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: jest.fn() });

    const { onChanged } = renderModal();

    const passwordInput = await screen.findByPlaceholderText('Current password');
    await userEvent.type(passwordInput, 'password');
    await userEvent.click(screen.getByRole('button', { name: 'Disable 2FA' }));

    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('Two‑factor authentication disabled');
    expect(screen.getByText('Two-factor authentication has been disabled.')).toBeInTheDocument();
  });

  describe('network errors', () => {
    it('shows network error when initiate throws', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock.mockRejectedValueOnce(new Error('Network failure'));

      renderModal();

      await waitFor(() => {
        expect(screen.getByText('Network error.')).toBeInTheDocument();
      });
    });

    it('shows network error when verify throws', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
        })
        .mockRejectedValueOnce(new Error('Network failure'));

      renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '123456');
      await userEvent.click(screen.getByRole('button', { name: 'Verify & Enable' }));

      await waitFor(() => {
        expect(screen.getByText('Network error.')).toBeInTheDocument();
      });
    });

    it('shows network error when disable throws', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
      fetchWithAuthMock.mockRejectedValueOnce(new Error('Network failure'));

      renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      await userEvent.type(passwordInput, 'password');
      await userEvent.click(screen.getByRole('button', { name: 'Disable 2FA' }));

      await waitFor(() => {
        expect(screen.getByText('Network error.')).toBeInTheDocument();
      });
    });

    it('shows network error when regenerate throws', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ backup_codes: ['code1'] }),
        })
        .mockRejectedValueOnce(new Error('Network failure'));

      renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '123456');
      await userEvent.click(screen.getByRole('button', { name: 'Verify & Enable' }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }));

      await waitFor(() => {
        expect(screen.getByText('Network error.')).toBeInTheDocument();
      });
    });
  });

  describe('error handling', () => {
    it('shows error when disable fails', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: false,
        json: jest.fn().mockResolvedValue({ detail: 'Wrong password' }),
      });

      renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      await userEvent.type(passwordInput, 'wrongpassword');
      await userEvent.click(screen.getByRole('button', { name: 'Disable 2FA' }));

      await waitFor(() => {
        expect(screen.getByText('Wrong password')).toBeInTheDocument();
      });
    });

    it('shows default error when disable fails without detail', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: false,
        json: jest.fn().mockResolvedValue({}),
      });

      renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      await userEvent.type(passwordInput, 'password');
      await userEvent.click(screen.getByRole('button', { name: 'Disable 2FA' }));

      await waitFor(() => {
        expect(screen.getByText('Failed to disable')).toBeInTheDocument();
      });
    });

    it('shows error when regenerate fails', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ backup_codes: ['code1'] }),
        })
        .mockResolvedValueOnce({
          ok: false,
          json: jest.fn().mockResolvedValue({}),
        });

      renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '123456');
      await userEvent.click(screen.getByRole('button', { name: 'Verify & Enable' }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Regenerate' })).toBeInTheDocument();
      });

      await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }));

      await waitFor(() => {
        expect(screen.getByText('Failed to regenerate')).toBeInTheDocument();
      });
    });
  });

  describe('keyboard handling', () => {
    it('submits verification on Enter key when code is valid', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ backup_codes: ['code1'] }),
        });

      const { onChanged } = renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '123456');
      await userEvent.keyboard('{Enter}');

      await waitFor(() => expect(onChanged).toHaveBeenCalled());
    });

    it('does not submit verification on Enter when code is too short', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
      });

      renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '123'); // Only 3 digits
      await userEvent.keyboard('{Enter}');

      // Should only have called initiate, not verify
      expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
    });

    it('submits disable on Enter key when password is provided', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: jest.fn() });

      const { onChanged } = renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      await userEvent.type(passwordInput, 'mypassword');
      await userEvent.keyboard('{Enter}');

      await waitFor(() => expect(onChanged).toHaveBeenCalled());
    });

    it('does not submit disable on Enter when password is empty', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });

      renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      passwordInput.focus();
      await userEvent.keyboard('{Enter}');

      // Should not have called any API
      expect(fetchWithAuthMock).not.toHaveBeenCalled();
    });

    it('closes modal on Escape key', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });

      const { onClose } = renderModal();

      await userEvent.keyboard('{Escape}');

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('verify fallback error messages', () => {
    it('shows default error message when verify returns ok:false without detail', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
        })
        .mockResolvedValueOnce({
          ok: false,
          json: jest.fn().mockResolvedValue({}),
        });

      renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '123456');
      await userEvent.click(screen.getByRole('button', { name: 'Verify & Enable' }));

      await waitFor(() => {
        expect(screen.getByText("That code didn't work. Please try again.")).toBeInTheDocument();
      });
    });

    it('shows default error message when verify response json() rejects', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock
        .mockResolvedValueOnce({
          ok: true,
          json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
        })
        .mockResolvedValueOnce({
          ok: false,
          json: jest.fn().mockRejectedValue(new Error('Invalid JSON')),
        });

      renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '654321');
      await userEvent.click(screen.getByRole('button', { name: 'Verify & Enable' }));

      await waitFor(() => {
        // .catch(() => ({})) returns empty object, so falls back to default message
        expect(screen.getByText("That code didn't work. Please try again.")).toBeInTheDocument();
      });
    });
  });

  describe('disable 2FA with json parse failure', () => {
    it('shows default error when disable response json() rejects', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: false,
        json: jest.fn().mockRejectedValue(new Error('Invalid JSON')),
      });

      renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      await userEvent.type(passwordInput, 'password');
      await userEvent.click(screen.getByRole('button', { name: 'Disable 2FA' }));

      await waitFor(() => {
        // .catch(() => ({})) returns empty object, so falls back to 'Failed to disable'
        expect(screen.getByText('Failed to disable')).toBeInTheDocument();
      });
    });
  });

  describe('close button', () => {
    it('closes modal via close button in show step', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
      });

      const { onClose } = renderModal();

      await screen.findByText('Secret (manual entry):');
      await userEvent.click(screen.getByRole('button', { name: 'Close' }));

      expect(onClose).toHaveBeenCalled();
    });

    it('closes modal via close button in disabled step', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: jest.fn() });

      const { onClose } = renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      await userEvent.type(passwordInput, 'password');
      await userEvent.click(screen.getByRole('button', { name: 'Disable 2FA' }));

      await screen.findByText('Two-factor authentication has been disabled.');
      await userEvent.click(screen.getByRole('button', { name: 'Close' }));

      expect(onClose).toHaveBeenCalled();
    });
  });
});
