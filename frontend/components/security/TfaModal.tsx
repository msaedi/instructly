'use client';

import { useEffect, useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { fetchWithAuth } from '@/lib/api';
import { toast } from 'sonner';
import { tfaStatusQueryKey, useTfaStatus } from '@/hooks/queries/useTfaStatus';
import Modal from '@/components/Modal';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';
import { queryKeys as sessionQueryKeys } from '@/src/api/queryKeys';
import { queryKeys as authContextQueryKeys } from '@/lib/react-query/queryClient';

type TfaSetupInitiateResponse = components['schemas']['TFASetupInitiateResponse'];
type TfaSetupVerifyResponse = components['schemas']['TFASetupVerifyResponse'];
type BackupCodesResponse = components['schemas']['BackupCodesResponse'];

type Props = {
  initialEnabled?: boolean | null;
  onClose: () => void;
  onChanged: () => void;
};

export default function TfaModal({ initialEnabled = null, onClose, onChanged }: Props) {
  const [step, setStep] = useState<'idle' | 'show' | 'verify' | 'enabled'>(
    initialEnabled === true ? 'enabled' : initialEnabled === false ? 'show' : 'idle'
  );
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requiresBackupCodeAcknowledgement, setRequiresBackupCodeAcknowledgement] = useState(false);
  const hasInitiatedRef = useRef(false);
  const queryClient = useQueryClient();
  const router = useRouter();

  const shouldLoadTfaStatus = initialEnabled === null;
  const { data: tfaStatus, isLoading: tfaStatusLoading } = useTfaStatus(shouldLoadTfaStatus);
  const resolvedInitialEnabled = initialEnabled ?? tfaStatus?.enabled ?? null;

  const clearClientAuthState = () => {
    queryClient.setQueryData(sessionQueryKeys.auth.me, null);
    queryClient.setQueryData(authContextQueryKeys.user, null);
    queryClient.removeQueries({ queryKey: sessionQueryKeys.auth.me });
    queryClient.removeQueries({ queryKey: authContextQueryKeys.user });
    queryClient.removeQueries({ queryKey: tfaStatusQueryKey });
    queryClient.removeQueries({ queryKey: ['phone-status'] });
  };

  const redirectToLoginAfterReauth = (message: string) => {
    clearClientAuthState();
    onChanged();
    onClose();
    toast.success(message);
    router.push('/login');
  };

  // Note: Escape key handling is now managed by Modal (Radix Dialog)

  useEffect(() => {
    if (initialEnabled === false && !hasInitiatedRef.current) {
      hasInitiatedRef.current = true;
      void initiate();
      return;
    }

    if (step !== 'idle' || resolvedInitialEnabled == null) {
      return;
    }

    if (resolvedInitialEnabled) {
      setStep('enabled');
      return;
    }

    setStep('show');
    if (!hasInitiatedRef.current) {
      hasInitiatedRef.current = true;
      void initiate();
    }
  }, [initialEnabled, resolvedInitialEnabled, step]);

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
      setRequiresBackupCodeAcknowledgement(true);
      setStep('enabled');
      queryClient.setQueryData(tfaStatusQueryKey, (prev?: { enabled?: boolean }) => ({
        ...prev,
        enabled: true,
      }));
      onChanged();
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
      queryClient.setQueryData(tfaStatusQueryKey, (prev?: { enabled?: boolean }) => ({
        ...prev,
        enabled: false,
      }));
      redirectToLoginAfterReauth('Two-factor authentication disabled. Please sign in again.');
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

  const acknowledgeBackupCodes = () => {
    redirectToLoginAfterReauth('Two-factor authentication enabled. Please sign in again.');
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Connect your authenticator app"
      description="Use an authenticator app to secure your account with one-time codes."
      size="md"
      autoHeight
      showCloseButton={!requiresBackupCodeAcknowledgement}
      closeOnEscape={!loading && !requiresBackupCodeAcknowledgement}
      closeOnBackdrop={!loading && !requiresBackupCodeAcknowledgement}
    >
      <div className="space-y-4">
        {error && <p className="text-sm text-red-600">{error}</p>}

        {step === 'idle' && shouldLoadTfaStatus && tfaStatusLoading ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Loading your two-factor authentication settings…
          </p>
        ) : null}

        {step === 'show' && (
          <>
            <p className="text-sm text-gray-700 dark:text-gray-300">
              <span className="font-medium">Step 1:</span> Scan the QR code using your authenticator app,
              then enter the 6-digit code from the app.
            </p>
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
              <div className="text-sm text-gray-700 dark:text-gray-300">
                <p className="font-medium">Secret (manual entry):</p>
                <p className="mt-1 break-all rounded bg-gray-50 dark:bg-gray-900 p-2 border text-gray-800 dark:text-gray-200">{secret}</p>
              </div>
            )}
            <div>
              <label htmlFor="tfa-code" className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                <span className="font-medium">Step 2:</span> Enter your 6-digit code
              </label>
              <input
                id="tfa-code"
                className="w-full rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm"
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
                className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 active:bg-gray-200 dark:active:bg-gray-600 transition-colors"
                onClick={onClose}
              >
                Close
              </button>
              <button
                type="button"
                className={`rounded-md px-4 py-2 text-sm font-semibold text-white transition-colors ${loading ? 'bg-purple-300' : 'bg-(--color-brand) hover:bg-purple-800 dark:hover:bg-purple-700 active:bg-purple-900'}`}
                onClick={verify}
                disabled={loading}
              >
                {loading ? 'Verifying…' : 'Verify'}
              </button>
            </div>
          </>
        )}

        {step === 'enabled' && (
          <>
            <p className="text-sm text-green-700 dark:text-emerald-400">Two-factor authentication is now enabled.</p>
            {backupCodes && backupCodes.length > 0 && (
              <div className="text-sm text-gray-700 dark:text-gray-300">
                <p className="font-medium mb-1">Backup codes (store securely):</p>
                <ul className="list-disc pl-5 space-y-0.5" aria-label="Backup codes">
                  {backupCodes.map((c) => (
                    <li key={c} className="font-mono text-xs">{c}</li>
                  ))}
                </ul>
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="rounded-md border px-3 py-1 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 active:bg-gray-200 dark:active:bg-gray-600 transition-colors"
                    onClick={() => {
                      void navigator.clipboard.writeText(backupCodes.join('\n'));
                      toast.success('Backup codes copied');
                    }}
                  >
                    Copy
                  </button>
                  <button
                    type="button"
                    className={`rounded-md border px-3 py-1 text-xs transition-colors ${loading ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-100 dark:hover:bg-gray-700 active:bg-gray-200 dark:active:bg-gray-600'}`}
                    onClick={() => void regen()}
                    disabled={loading}
                  >
                    {loading ? 'Working…' : 'Regenerate'}
                  </button>
                </div>
              </div>
            )}
            {requiresBackupCodeAcknowledgement ? (
              <div className="mt-6 border-t pt-4 space-y-3">
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  Save these backup codes somewhere secure before continuing. You will need them if you lose access to your authenticator app.
                </p>
                <button
                  type="button"
                  className="insta-primary-btn inline-flex w-full items-center justify-center rounded-md px-4 py-2 text-sm font-semibold text-white transition focus:outline-none  disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={acknowledgeBackupCodes}
                  disabled={loading}
                >
                  I&apos;ve saved my backup codes
                </button>
              </div>
            ) : (
              <div className="mt-6 border-t pt-4 space-y-3">
                <p className="text-sm text-gray-700 dark:text-gray-300">To disable 2FA, confirm your password.</p>
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
                    className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 active:bg-gray-200 dark:active:bg-gray-600 transition-colors"
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
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
