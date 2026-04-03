import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TfaModal from '../TfaModal';
import { fetchWithAuth } from '@/lib/api';
import { useTfaStatus } from '@/hooks/queries/useTfaStatus';
import { toast } from 'sonner';
import { queryKeys as sessionQueryKeys } from '@/src/api/queryKeys';
import { queryKeys as authContextQueryKeys } from '@/lib/react-query/queryClient';

const pushMock = jest.fn();

jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));

jest.mock('@/hooks/queries/useTfaStatus', () => ({
  useTfaStatus: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: pushMock,
  }),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const fetchWithAuthMock = fetchWithAuth as jest.Mock;
const useTfaStatusMock = useTfaStatus as jest.Mock;

const renderModal = (props?: {
  initialEnabled?: boolean | null;
  onClose?: jest.Mock;
  onChanged?: jest.Mock;
}) => {
  const onClose = props?.onClose ?? jest.fn();
  const onChanged = props?.onChanged ?? jest.fn();
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  queryClient.setQueryData(sessionQueryKeys.auth.me, { id: 'session-user' });
  queryClient.setQueryData(authContextQueryKeys.user, { id: 'legacy-user' });
  queryClient.setQueryData(['phone-status'], { phone_number: '+12125551001', verified: true });

  render(
    <QueryClientProvider client={queryClient}>
      <TfaModal
        {...(props && 'initialEnabled' in props
          ? { initialEnabled: props.initialEnabled ?? null }
          : {})}
        onClose={onClose}
        onChanged={onChanged}
      />
    </QueryClientProvider>
  );

  return { onClose, onChanged, queryClient };
};

describe('TfaModal', () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    useTfaStatusMock.mockReset();
    pushMock.mockReset();
    (toast.success as jest.Mock).mockReset();
    (toast.error as jest.Mock).mockReset();

    Object.assign(navigator, {
      clipboard: {
        writeText: jest.fn().mockResolvedValue(undefined),
      },
    });

    useTfaStatusMock.mockReturnValue({
      data: { enabled: false },
      isLoading: false,
      isSuccess: true,
    });
  });

  it('initiates setup immediately when the parent already knows 2FA is disabled', async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
    });

    renderModal({ initialEnabled: false });

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith('/api/v1/2fa/setup/initiate', {
        method: 'POST',
      });
    });
    expect(useTfaStatusMock).toHaveBeenCalledWith(false);
    expect(await screen.findByText('Secret (manual entry):')).toBeInTheDocument();
  });

  it('shows a loading state while waiting for a fallback 2FA status check', () => {
    useTfaStatusMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isSuccess: false,
    });

    renderModal({ initialEnabled: null });

    expect(
      screen.getByText('Loading your two-factor authentication settings…')
    ).toBeInTheDocument();
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

    expect(screen.getByRole('dialog', { name: 'Connect your authenticator app' })).toBeInTheDocument();
    expect(
      screen.getByText(/Scan the QR code using your authenticator app, then enter the 6-digit code from the app\./i, {
        selector: 'p',
      })
    ).toBeInTheDocument();
    expect(await screen.findByText('Secret (manual entry):')).toBeInTheDocument();
    expect(screen.getByLabelText(/Step 2: Enter your 6-digit code/i)).toBeInTheDocument();
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
    await userEvent.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(screen.getByText('Invalid code')).toBeInTheDocument();
    });
  });

  it('shows backup codes first, keeps copy/regenerate, then redirects after acknowledgement', async () => {
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

    const { onChanged, onClose, queryClient } = renderModal();

    const codeInput = await screen.findByPlaceholderText('123 456');
    await userEvent.type(codeInput, '123456');
    await userEvent.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(screen.getByText('code1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: "I've saved my backup codes" })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Close$/ })).not.toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalledWith('Two-factor authentication enabled. Please sign in again.');

    await userEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('code1\ncode2');

    await userEvent.click(screen.getByRole('button', { name: 'Regenerate' }));
    await waitFor(() => {
      expect(screen.getByText('code3')).toBeInTheDocument();
    });

    await userEvent.keyboard('{Escape}');
    expect(onClose).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: "I've saved my backup codes" }));

    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledTimes(2);
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(pushMock).toHaveBeenCalledWith('/login');
    });
    expect(toast.success).toHaveBeenCalledWith('Two-factor authentication enabled. Please sign in again.');
    expect(queryClient.getQueryData(sessionQueryKeys.auth.me)).toBeUndefined();
    expect(queryClient.getQueryData(authContextQueryKeys.user)).toBeUndefined();
  });

  it('redirects to login immediately after disabling 2FA and clears session cache', async () => {
    useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: jest.fn() });

    const { onChanged, onClose, queryClient } = renderModal();

    const passwordInput = await screen.findByPlaceholderText('Current password');
    await userEvent.type(passwordInput, 'password');
    await userEvent.click(screen.getByRole('button', { name: 'Disable 2FA' }));

    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(pushMock).toHaveBeenCalledWith('/login');
    });
    expect(toast.success).toHaveBeenCalledWith('Two-factor authentication disabled. Please sign in again.');
    expect(screen.queryByText('Two-factor authentication has been disabled.')).not.toBeInTheDocument();
    expect(queryClient.getQueryData(sessionQueryKeys.auth.me)).toBeUndefined();
    expect(queryClient.getQueryData(authContextQueryKeys.user)).toBeUndefined();
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
      await userEvent.click(screen.getByRole('button', { name: 'Verify' }));

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
      await userEvent.click(screen.getByRole('button', { name: 'Verify' }));

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
      await userEvent.click(screen.getByRole('button', { name: 'Verify' }));

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

      await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    });

    it('does not submit verification on Enter when code is too short', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: false }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({
        ok: true,
        json: jest.fn().mockResolvedValue({ qr_code_data_url: 'data:image/png', secret: 'ABC123' }),
      });

      renderModal();

      const codeInput = await screen.findByPlaceholderText('123 456');
      await userEvent.type(codeInput, '123');
      await userEvent.keyboard('{Enter}');

      expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
    });

    it('submits disable on Enter key when password is provided', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });
      fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: jest.fn() });

      const { onChanged } = renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      await userEvent.type(passwordInput, 'mypassword');
      await userEvent.keyboard('{Enter}');

      await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
      expect(pushMock).toHaveBeenCalledWith('/login');
    });

    it('does not submit disable on Enter when password is empty', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });

      renderModal();

      const passwordInput = await screen.findByPlaceholderText('Current password');
      passwordInput.focus();
      await userEvent.keyboard('{Enter}');

      expect(fetchWithAuthMock).not.toHaveBeenCalled();
    });

    it('closes modal on Escape key when acknowledgement is not required', async () => {
      useTfaStatusMock.mockReturnValue({ data: { enabled: true }, isSuccess: true });

      const { onClose } = renderModal();

      await userEvent.keyboard('{Escape}');

      expect(onClose).toHaveBeenCalledTimes(1);
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
      await userEvent.click(screen.getByRole('button', { name: 'Verify' }));

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
      await userEvent.click(screen.getByRole('button', { name: 'Verify' }));

      await waitFor(() => {
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

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});
