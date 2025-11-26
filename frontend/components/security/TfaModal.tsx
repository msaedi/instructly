'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchWithAuth } from '@/lib/api';
import { toast } from 'sonner';

type Props = {
  onClose: () => void;
  onChanged: () => void;
};

export default function TfaModal({ onClose, onChanged }: Props) {
  const [mounted, setMounted] = useState(false);
  const [step, setStep] = useState<'idle' | 'show' | 'verify' | 'enabled' | 'disabled'>('idle');
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMounted(true);
    (async () => {
      try {
        const res = await fetchWithAuth('/api/v1/2fa/status');
        if (!res.ok) return;
        const data = await res.json();
        if (data.enabled) {
          setStep('enabled');
        } else {
          setStep('show');
          await initiate();
        }
      } catch {
        // ignore status load errors; modal buttons allow retry
      }
    })();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

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
      const data = await res.json();
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
        const b = await res.json().catch(() => ({}));
        setError((b as { detail?: string }).detail || "That code didn't work. Please try again.");
        setLoading(false);
        return;
      }
      const data = await res.json();
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
        const b = await res.json().catch(() => ({}));
        setError((b as { detail?: string }).detail || 'Failed to disable');
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
      const data = await res.json();
      setBackupCodes(data.backup_codes || []);
      toast.success('Backup codes regenerated');
    } catch {
      setError('Network error.');
    } finally {
      setLoading(false);
    }
  };

  if (!mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Two-Factor Authentication</h3>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </div>
        {step === 'show' && (
          <div className="space-y-4">
            {qr && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={qr} alt="QR code" className="mx-auto h-40 w-40" />
            )}
            {secret && (
              <div className="text-sm text-gray-700">
                <p className="font-medium">Secret (manual entry):</p>
                <p className="mt-1 break-all rounded bg-gray-50 p-2 border text-gray-800">{secret}</p>
              </div>
            )}
            <div>
              <label className="block text-xs text-gray-500 mb-1">Enter 6-digit code</label>
              <input
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
              />
            </div>
            <div className="flex justify-end gap-3">
              <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
              <button className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-purple-300' : 'bg-[#7E22CE] hover:bg-[#7E22CE] active:bg-purple-900'}`} onClick={verify} disabled={loading}>
                {loading ? 'Verifying…' : 'Verify & Enable'}
              </button>
            </div>
          </div>
        )}
        {step === 'enabled' && (
          <div className="space-y-4">
            <p className="text-sm text-green-700">Two-factor authentication is now enabled.</p>
            {backupCodes && backupCodes.length > 0 && (
              <div className="text-sm text-gray-700">
                <p className="font-medium mb-1">Backup codes (store securely):</p>
                <ul className="list-disc pl-5 space-y-0.5">
                  {backupCodes.map((c) => (<li key={c} className="font-mono text-xs">{c}</li>))}
                </ul>
                <div className="mt-2 flex gap-2">
                  <button
                    className="rounded-md border px-3 py-1 text-xs hover:bg-gray-100 active:bg-gray-200 transition-colors"
                    onClick={() => { void navigator.clipboard.writeText(backupCodes.join('\n')); toast.success('Backup codes copied'); }}
                  >
                    Copy
                  </button>
                  <button
                    className={`rounded-md border px-3 py-1 text-xs transition-colors ${loading ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-100 active:bg-gray-200'}`}
                    onClick={() => void regen()}
                    disabled={loading}
                  >
                    {loading ? 'Working…' : 'Regenerate'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        {step === 'disabled' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-700">Two-factor authentication has been disabled.</p>
            <div className="flex justify-end gap-3">
              <button autoFocus className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
            </div>
          </div>
        )}
        {step === 'enabled' && (
          <div className="mt-6 border-t pt-4 space-y-3">
            <p className="text-sm text-gray-700">To disable 2FA, confirm your password.</p>
            <input
              type="password"
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
            />
            <div className="flex justify-end gap-3">
              <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
              <button className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-red-300' : 'bg-red-600 hover:bg-red-700 active:bg-red-800'}`} onClick={() => void disable()} disabled={loading}>
                {loading ? 'Disabling…' : 'Disable 2FA'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
