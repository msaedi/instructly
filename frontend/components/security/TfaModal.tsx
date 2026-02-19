'use client';

import { useEffect, useState, useRef } from 'react';
import Image from 'next/image';
import { fetchWithAuth } from '@/lib/api';
import { toast } from 'sonner';
import { useTfaStatus } from '@/hooks/queries/useTfaStatus';
import Modal from '@/components/Modal';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

type TfaSetupInitiateResponse = components['schemas']['TFASetupInitiateResponse'];
type TfaSetupVerifyResponse = components['schemas']['TFASetupVerifyResponse'];
type BackupCodesResponse = components['schemas']['BackupCodesResponse'];

type Props = {
  onClose: () => void;
  onChanged: () => void;
};

export default function TfaModal({ onClose, onChanged }: Props) {
  const [step, setStep] = useState<'idle' | 'show' | 'verify' | 'enabled' | 'disabled'>('idle');
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasInitiatedRef = useRef(false);

  // Use React Query hook for 2FA status (deduplicates calls)
  const { data: tfaStatus, isSuccess: tfaStatusLoaded } = useTfaStatus();

  // Note: Escape key handling is now managed by Modal (Radix Dialog)

  // Determine initial step based on 2FA status from hook
  useEffect(() => {
    if (!tfaStatusLoaded || step !== 'idle') return;
    if (tfaStatus?.enabled) {
      setStep('enabled');
    } else {
      setStep('show');
      // Auto-initiate setup if 2FA not enabled (only once)
      if (!hasInitiatedRef.current) {
        hasInitiatedRef.current = true;
        void initiate();
      }
    }
  }, [tfaStatusLoaded, tfaStatus, step]);

  const initiate = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetchWithAuth('/api/v1/2fa/setup/initiate', { method: 'POST' });
      if (!res.ok) {
        setError('Failed to initiate 2FA.');
        setLoading(false);
        return;
      }
      const data = (await res.json()) as TfaSetupInitiateResponse;
      setQr(data.qr_code_data_url);
      setSecret(data.secret);
      setStep('show');
    } catch {
      setError('Network error.');
    } finally {
      setLoading(false);
    }
  };

  const verify = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetchWithAuth('/api/v1/2fa/setup/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      if (!res.ok) {
        const b = (await res.json().catch(() => ({}))) as ApiErrorResponse;
        setError(extractApiErrorMessage(b, "That code didn't work. Please try again."));
        setLoading(false);
        return;
      }
      const data = (await res.json()) as TfaSetupVerifyResponse;
      setBackupCodes(data.backup_codes || []);
      setStep('enabled');
      onChanged();
      toast.success('Two‑factor authentication enabled');
    } catch {
      setError('Network error.');
    } finally {
      setLoading(false);
    }
  };

  const disable = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetchWithAuth('/api/v1/2fa/disable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword }),
      });
      if (!res.ok) {
        const b = (await res.json().catch(() => ({}))) as ApiErrorResponse;
        setError(extractApiErrorMessage(b, 'Failed to disable'));
        setLoading(false);
        return;
      }
      setStep('disabled');
      onChanged();
      toast.success('Two‑factor authentication disabled');
    } catch {
      setError('Network error.');
    } finally {
      setLoading(false);
    }
  };

  const regen = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetchWithAuth('/api/v1/2fa/regenerate-backup-codes', { method: 'POST' });
      if (!res.ok) {
        setError('Failed to regenerate');
        setLoading(false);
        return;
      }
      const data = (await res.json()) as BackupCodesResponse;
      setBackupCodes(data.backup_codes || []);
      toast.success('Backup codes regenerated');
    } catch {
      setError('Network error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Two-Factor Authentication"
      description="Manage two-factor authentication settings for your account"
      size="md"
      autoHeight
      closeOnEscape={!loading}
      closeOnBackdrop={!loading}
    >
      <div className="space-y-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        {step === 'show' && (
          <>
            {qr && (
              <Image
                src={qr}
                alt="QR code for authenticator app"
                width={160}
                height={160}
                unoptimized
                className="mx-auto h-40 w-40"
              />
            )}
            {secret && (
              <div className="text-sm text-gray-700">
                <p className="font-medium">Secret (manual entry):</p>
                <p className="mt-1 break-all rounded bg-gray-50 p-2 border text-gray-800">{secret}</p>
              </div>
            )}
            <div>
              <label htmlFor="tfa-code" className="block text-xs text-gray-500 mb-1">
                Enter 6-digit code
              </label>
              <input
                id="tfa-code"
                className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !loading && code.trim().length >= 6) {
                    e.preventDefault();
                    void verify();
                  }
                }}
                placeholder="123 456"
                autoComplete="one-time-code"
                inputMode="numeric"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors"
                onClick={onClose}
              >
                Close
              </button>
              <button
                type="button"
                className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-purple-300' : 'bg-[#7E22CE] hover:bg-[#7E22CE] active:bg-purple-900'}`}
                onClick={verify}
                disabled={loading}
              >
                {loading ? 'Verifying…' : 'Verify & Enable'}
              </button>
            </div>
          </>
        )}

        {step === 'enabled' && (
          <>
            <p className="text-sm text-green-700">Two-factor authentication is now enabled.</p>
            {backupCodes && backupCodes.length > 0 && (
              <div className="text-sm text-gray-700">
                <p className="font-medium mb-1">Backup codes (store securely):</p>
                <ul className="list-disc pl-5 space-y-0.5" aria-label="Backup codes">
                  {backupCodes.map((c) => (
                    <li key={c} className="font-mono text-xs">{c}</li>
                  ))}
                </ul>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="rounded-md border px-3 py-1 text-xs hover:bg-gray-100 active:bg-gray-200 transition-colors"
                    onClick={() => {
                      void navigator.clipboard.writeText(backupCodes.join('\n'));
                      toast.success('Backup codes copied');
                    }}
                  >
                    Copy
                  </button>
                  <button
                    type="button"
                    className={`rounded-md border px-3 py-1 text-xs transition-colors ${loading ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-100 active:bg-gray-200'}`}
                    onClick={() => void regen()}
                    disabled={loading}
                  >
                    {loading ? 'Working…' : 'Regenerate'}
                  </button>
                </div>
              </div>
            )}
            <div className="mt-6 border-t pt-4 space-y-3">
              <p className="text-sm text-gray-700">To disable 2FA, confirm your password.</p>
              <input
                type="password"
                id="disable-password"
                className="w-full rounded-md border px-3 py-2 text-sm"
                placeholder="Current password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !loading && currentPassword.trim().length > 0) {
                    e.preventDefault();
                    void disable();
                  }
                }}
                autoComplete="current-password"
              />
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors"
                  onClick={onClose}
                >
                  Close
                </button>
                <button
                  type="button"
                  className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-red-300' : 'bg-red-600 hover:bg-red-700 active:bg-red-800'}`}
                  onClick={() => void disable()}
                  disabled={loading}
                >
                  {loading ? 'Disabling…' : 'Disable 2FA'}
                </button>
              </div>
            </div>
          </>
        )}

        {step === 'disabled' && (
          <>
            <p className="text-sm text-gray-700">Two-factor authentication has been disabled.</p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                autoFocus
                className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors"
                onClick={onClose}
              >
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
