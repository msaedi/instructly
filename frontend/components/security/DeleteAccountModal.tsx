'use client';

import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { fetchAPI, fetchWithAuth } from '@/lib/api';
import type { ApiErrorResponse } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

type Props = {
  email: string;
  onClose: () => void;
  onDeleted: () => void;
};

export default function DeleteAccountModal({ email, onClose, onDeleted }: Props) {
  const [password, setPassword] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const canSubmit = confirmText.trim().toUpperCase() === 'DELETE' && password.length >= 6 && !submitting;

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Verify password silently (backend expects form-encoded OAuth2 fields)
      const loginRes = await fetchAPI('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password }).toString(),
      });
      if (!loginRes.ok) {
        setError('Incorrect password.');
        setSubmitting(false);
        return;
      }

      // Soft delete account
      const delRes = await fetchWithAuth('/api/v1/privacy/delete/me', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delete_account: true }),
      });
      if (!delRes.ok) {
        try {
          const body = (await delRes.json()) as ApiErrorResponse;
          if (delRes.status === 400 && body?.detail) {
            setError(extractApiErrorMessage(body));
          } else {
            setError('Failed to delete account. Please try again later.');
          }
        } catch {
          setError('Failed to delete account. Please try again later.');
        }
        setSubmitting(false);
        return;
      }
      onDeleted();
    } catch {
      setError('Unexpected error. Please try again.');
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Delete Account</h3>
          <p className="mt-2 text-sm text-gray-600">This action cannot be undone. Type DELETE to confirm and enter your password.</p>
        </div>
        <div className="space-y-3">
          <input
            placeholder="Type DELETE to confirm"
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
          />
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder="Password"
              className="w-full rounded-md border px-3 py-2 pr-10 text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 focus-visible:ring-2 focus-visible:ring-purple-600 focus-visible:ring-offset-1 focus-visible:text-[#7E22CE]"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors" onClick={onClose} disabled={submitting}>Cancel</button>
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium border ${canSubmit ? 'bg-white border-[#7E22CE] text-[#7E22CE] hover:bg-purple-50' : 'bg-gray-100 border-gray-300 text-gray-400 cursor-not-allowed'}`}
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {submitting ? 'Deleting…' : 'Delete My Account'}
          </button>
        </div>
      </div>
    </div>
  );
}
