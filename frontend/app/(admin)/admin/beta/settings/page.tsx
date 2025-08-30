'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { getBetaSettings, updateBetaSettings, type BetaSettings } from '@/lib/betaApi';
import { API_URL } from '@/lib/api';
import { logger } from '@/lib/logger';

export default function BetaSettingsPage() {
  const { isAdmin, isLoading } = useAdminAuth();
  const { logout } = useAuth();
  const [form, setForm] = useState<BetaSettings>({ beta_disabled: false, beta_phase: 'instructor_only', allow_signup_without_invite: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const data = await getBetaSettings();
        if (mounted) setForm(data);
      } catch (e) {
        logger.error('Failed to load beta settings', e);
        setMessage('Failed to load settings');
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  const onChange = (field: keyof BetaSettings, value: boolean | string) => {
    setForm((prev) => ({ ...prev, [field]: value } as BetaSettings));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateBetaSettings(form);
      setForm(updated);
      setMessage('Settings saved');
    } catch (e) {
      logger.error('Failed to save beta settings', e);
      setMessage('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) return null;
  if (!isAdmin) return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
      <div className="text-center text-sm text-gray-600 dark:text-gray-300">You do not have access to this page.</div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">iNSTAiNSTRU</Link>
              <h1 className="text-xl font-semibold">Beta Settings</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button onClick={logout} className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer">Log out</button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-4 lg:col-span-4">
            <AdminSidebar />
          </aside>
          <section className="col-span-12 md:col-span-8 lg:col-span-8">
            {loading ? (
              <div className="text-sm text-gray-500">Loading...</div>
            ) : (
              <form onSubmit={onSubmit} className="max-w-xl space-y-4 bg-white/60 dark:bg-gray-900/40 backdrop-blur p-4 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
                <div className="flex items-center justify-between">
                  <label className="font-medium">Disable Beta</label>
                  <input
                    type="checkbox"
                    checked={form.beta_disabled}
                    onChange={(e) => onChange('beta_disabled', e.target.checked)}
                    className="h-4 w-4"
                  />
                </div>

                <div>
                  <label className="font-medium block mb-1">Beta Phase</label>
                  <select
                    value={form.beta_phase}
                    onChange={(e) => onChange('beta_phase', e.target.value)}
                    className="w-full rounded-md border-gray-300 dark:bg-gray-800 dark:border-gray-700"
                  >
                    <option value="instructor_only">instructor_only</option>
                    <option value="open_beta">open_beta</option>
                  </select>
                </div>

                <div className="flex items-center justify-between">
                  <label className="font-medium">Allow signup without invite</label>
                  <input
                    type="checkbox"
                    checked={form.allow_signup_without_invite}
                    onChange={(e) => onChange('allow_signup_without_invite', e.target.checked)}
                    className="h-4 w-4"
                  />
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-4 py-2 rounded-md bg-indigo-600 text-white disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : 'Save Settings'}
                  </button>
                  {message && <span className="text-sm text-gray-600 dark:text-gray-300">{message}</span>}
                </div>
              </form>
            )}

            <BetaPhaseInfo />
          </section>
        </div>
      </main>
    </div>
  );
}

function BetaPhaseInfo() {
  const [phase, setPhase] = useState<string | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/health`, { cache: 'no-store' });
        const header = res.headers.get('x-beta-phase');
        setPhase(header);
      } catch {
        setPhase(null);
      }
    })();
  }, []);
  return (
    <div className="mt-6 text-sm text-gray-600 dark:text-gray-300">
      <span className="font-medium">Current server phase header:</span> {phase ?? 'n/a'}
    </div>
  );
}
