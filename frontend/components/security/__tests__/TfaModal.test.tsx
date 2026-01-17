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
});
