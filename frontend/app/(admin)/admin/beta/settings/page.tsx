'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { getBetaSettings, updateBetaSettings, type BetaSettings } from '@/lib/betaApi';
import { API_URL } from '@/lib/api';
import { logger } from '@/lib/logger';
import * as Switch from '@radix-ui/react-switch';
import * as Select from '@radix-ui/react-select';
import { ChevronDown, Check } from 'lucide-react';

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
                  <label className="font-medium" htmlFor="beta-disabled">Disable Beta</label>
                  <Switch.Root
                    id="beta-disabled"
                    checked={form.beta_disabled}
                    onCheckedChange={(v) => onChange('beta_disabled', v)}
                    className="relative inline-flex h-6 w-11 items-center rounded-full bg-gray-300 dark:bg-gray-700 data-[state=checked]:bg-indigo-600 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    aria-label="Disable Beta"
                  >
                    <Switch.Thumb className="block h-5 w-5 rounded-full bg-white shadow transition-transform translate-x-1 data-[state=checked]:translate-x-5" />
                  </Switch.Root>
                </div>

                <div>
                  <label className="font-medium block mb-1">Beta Phase</label>
                  <Select.Root value={form.beta_phase} onValueChange={(v) => onChange('beta_phase', v)}>
                    <Select.Trigger className="inline-flex items-center justify-between w-full rounded-lg px-3 py-2 ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800">
                      <Select.Value />
                      <Select.Icon>
                        <ChevronDown className="h-4 w-4 text-gray-500" />
                      </Select.Icon>
                    </Select.Trigger>
                    <Select.Portal>
                      <Select.Content className="overflow-hidden rounded-md bg-white dark:bg-gray-800 shadow ring-1 ring-gray-200 dark:ring-gray-700">
                        <Select.Viewport className="p-1">
                          <Select.Item value="instructor_only" className="relative flex select-none items-center rounded px-2 py-1.5 text-sm text-gray-800 dark:text-gray-200 data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-700 outline-none cursor-pointer">
                            <Select.ItemText>instructor_only</Select.ItemText>
                            <Select.ItemIndicator className="absolute right-2">
                              <Check className="h-4 w-4" />
                            </Select.ItemIndicator>
                          </Select.Item>
                          <Select.Item value="open_beta" className="relative flex select-none items-center rounded px-2 py-1.5 text-sm text-gray-800 dark:text-gray-200 data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-700 outline-none cursor-pointer">
                            <Select.ItemText>open_beta</Select.ItemText>
                            <Select.ItemIndicator className="absolute right-2">
                              <Check className="h-4 w-4" />
                            </Select.ItemIndicator>
                          </Select.Item>
                        </Select.Viewport>
                      </Select.Content>
                    </Select.Portal>
                  </Select.Root>
                </div>

                <div className="flex items-center justify-between">
                  <label className="font-medium" htmlFor="allow-signup">Allow signup without invite</label>
                  <Switch.Root
                    id="allow-signup"
                    checked={form.allow_signup_without_invite}
                    onCheckedChange={(v) => onChange('allow_signup_without_invite', v)}
                    className="relative inline-flex h-6 w-11 items-center rounded-full bg-gray-300 dark:bg-gray-700 data-[state=checked]:bg-indigo-600 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400"
                    aria-label="Allow signup without invite"
                  >
                    <Switch.Thumb className="block h-5 w-5 rounded-full bg-white shadow transition-transform translate-x-1 data-[state=checked]:translate-x-5" />
                  </Switch.Root>
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
