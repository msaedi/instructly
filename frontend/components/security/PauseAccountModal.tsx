'use client';

import { useState } from 'react';
import { fetchWithAuth } from '@/lib/api';

export default function PauseAccountModal({ onClose, onPaused }: { onClose: () => void; onPaused: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pause = async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetchWithAuth('/api/account/suspend', { method: 'POST' });
      if (res.ok) { onPaused(); return; }
      if (res.status === 409) {
        const body = await res.json().catch(() => ({} as Record<string, unknown>));
        setError(typeof body?.detail === 'string' ? body.detail : 'Cannot pause while future bookings exist.');
      } else {
        setError('Failed to pause account. Please try again.');
      }
    } catch { setError('Network error.'); } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Pause account</h3>
        <p className="text-sm text-gray-600">You won’t receive new bookings while paused. Existing bookings are unaffected.</p>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        <div className="mt-5 flex justify-end gap-3">
          <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-50" onClick={onClose} disabled={loading}>Cancel</button>
          <button className={`rounded-md px-4 py-2 text-sm text-white ${loading ? 'bg-purple-300' : 'bg-[#7E22CE] hover:bg-[#7E22CE]'}`} onClick={() => void pause()} disabled={loading}>
            {loading ? 'Pausing…' : 'Pause'}
          </button>
        </div>
      </div>
    </div>
  );
}
