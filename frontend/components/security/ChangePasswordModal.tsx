'use client';

import { useState } from 'react';
import { fetchWithAuth } from '@/lib/api';
import type { ApiErrorResponse } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

export default function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = !loading && newPassword.length >= 8 && newPassword === confirmPassword && currentPassword.length >= 6;

  const submit = async () => {
    if (!canSubmit) return;
    setLoading(true); setError(null);
    try {
      const res = await fetchWithAuth('/api/v1/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!res.ok) {
        const b = (await res.json().catch(() => ({}))) as ApiErrorResponse;
        setError(extractApiErrorMessage(b, 'Failed to change password.'));
        setLoading(false);
        return;
      }
      onClose();
    } catch { setError('Network error.'); setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <h3 className="text-lg font-semibold text-gray-900">Change password</h3>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Current password</label>
            <input type="password" className="w-full rounded-md border px-3 py-2 text-sm" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">New password</label>
            <input type="password" className="w-full rounded-md border px-3 py-2 text-sm" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Confirm new password</label>
            <input type="password" className="w-full rounded-md border px-3 py-2 text-sm" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-50" onClick={onClose} disabled={loading}>Cancel</button>
          <button className={`rounded-md px-4 py-2 text-sm text-white ${canSubmit ? 'bg-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-purple-300 cursor-not-allowed'}`} onClick={() => void submit()} disabled={!canSubmit}>
            {loading ? 'Saving…' : 'Save password'}
          </button>
        </div>
      </div>
    </div>
  );
}
