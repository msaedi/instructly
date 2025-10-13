'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { logger } from '@/lib/logger';

type TierConfig = {
  min: number;
  max: number | null;
  pct: number;
};

type PriceFloorConfig = {
  private_in_person: number;
  private_remote: number;
};

type StudentCreditCycle = {
  cycle_len: number;
  mod10: number;
  cents10: number;
  mod20: number;
  cents20: number;
};

type PricingConfig = {
  student_fee_pct: number;
  instructor_tiers: TierConfig[];
  tier_activity_window_days: number;
  tier_stepdown_max: number;
  tier_inactivity_reset_days: number;
  price_floor_cents: PriceFloorConfig;
  student_credit_cycle: StudentCreditCycle;
};

type PricingConfigResponse = {
  config: PricingConfig;
  updated_at: string | null;
};

const DEFAULT_CONFIG: PricingConfig = {
  student_fee_pct: 0.12,
  instructor_tiers: [
    { min: 1, max: 4, pct: 0.15 },
    { min: 5, max: 10, pct: 0.12 },
    { min: 11, max: null, pct: 0.1 },
  ],
  tier_activity_window_days: 30,
  tier_stepdown_max: 1,
  tier_inactivity_reset_days: 90,
  price_floor_cents: { private_in_person: 8000, private_remote: 6000 },
  student_credit_cycle: {
    cycle_len: 11,
    mod10: 5,
    cents10: 1000,
    mod20: 0,
    cents20: 2000,
  },
};

function formatTimestamp(value: string | null): string {
  if (!value) return 'n/a';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
}

export default function PricingSettingsPage() {
  const { isAdmin, isLoading } = useAdminAuth();
  const { logout } = useAuth();

  const [config, setConfig] = useState<PricingConfig>(DEFAULT_CONFIG);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchConfig() {
      try {
        const response = await fetch('/api/admin/config/pricing', {
          credentials: 'include',
        });
        if (!response.ok) {
          throw new Error(`Failed to fetch config (${response.status})`);
        }
        const payload = (await response.json()) as PricingConfigResponse;
        if (!cancelled && payload?.config) {
          setConfig(payload.config);
          setUpdatedAt(payload.updated_at);
        }
      } catch (err) {
        logger.error('Failed to load pricing config', err as Error);
        if (!cancelled) {
          setError('Failed to load pricing configuration');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    if (isAdmin) {
      void fetchConfig();
    } else if (!isLoading) {
      setLoading(false);
    }

    return () => {
      cancelled = true;
    };
  }, [isAdmin, isLoading]);

  const jsonPreview = useMemo(() => JSON.stringify(config, null, 2), [config]);

  const updateTier = (index: number, field: keyof TierConfig, value: string) => {
    setConfig((prev) => ({
      ...prev,
      instructor_tiers: prev.instructor_tiers.map((tier, idx) => {
        if (idx !== index) {
          return tier;
        }
        const updated: TierConfig = { ...tier };
        if (field === 'max') {
          updated.max = value.trim() === '' ? null : Number(value);
        } else if (field === 'pct') {
          updated.pct = Number(value);
        } else if (field === 'min') {
          updated.min = Number(value);
        }
        return updated;
      }),
    }));
  };

  const updatePriceFloor = (field: keyof PriceFloorConfig, value: string) => {
    setConfig((prev) => ({
      ...prev,
      price_floor_cents: {
        ...prev.price_floor_cents,
        [field]: Number(value),
      },
    }));
  };

  const updateCreditCycle = (field: keyof StudentCreditCycle, value: string) => {
    setConfig((prev) => ({
      ...prev,
      student_credit_cycle: {
        ...prev.student_credit_cycle,
        [field]: Number(value),
      },
    }));
  };

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const response = await fetch('/api/admin/config/pricing', {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail = payload?.detail ?? `HTTP ${response.status}`;
        throw new Error(String(detail));
      }

      const payload = (await response.json()) as PricingConfigResponse;
      setConfig(payload.config);
      setUpdatedAt(payload.updated_at);
      setMessage('Pricing configuration saved');
    } catch (err) {
      logger.error('Failed to save pricing config', err as Error);
      setError((err as Error).message || 'Failed to save pricing configuration');
    } finally {
      setSaving(false);
    }
  };

  if (isLoading || loading) {
    return null;
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
        <div className="text-center text-sm text-gray-600 dark:text-gray-300">You do not have access to this page.</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">iNSTAiNSTRU</Link>
              <h1 className="text-xl font-semibold">Pricing Settings</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={logout}
                className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer"
              >
                Log out
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 md:col-span-3 lg:col-span-3">
            <AdminSidebar />
          </aside>

          <section className="col-span-12 md:col-span-9 lg:col-span-9 space-y-6">
            <div className="bg-white/70 dark:bg-gray-900/40 backdrop-blur rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Pricing Configuration</h2>
                <span className="text-xs text-gray-500">Last updated: {formatTimestamp(updatedAt)}</span>
              </div>

              <form className="space-y-6" onSubmit={handleSubmit}>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Student Booking Protection Fee (%)</label>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={config.student_fee_pct}
                    onChange={(e) => setConfig({ ...config, student_fee_pct: Number(e.target.value) })}
                    className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">Instructor Tiers</h3>
                  <p className="text-xs text-gray-500 mb-2">Percentages are expressed as decimals (e.g. 0.15 = 15%).</p>
                  <div className="space-y-3">
                    {config.instructor_tiers.map((tier, index) => (
                      <div key={index} className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                        <div>
                          <label className="block text-xs font-medium text-gray-500">Min</label>
                          <input
                            type="number"
                            min={0}
                            value={tier.min}
                            onChange={(e) => updateTier(index, 'min', e.target.value)}
                            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500">Max</label>
                          <input
                            type="number"
                            min={tier.min}
                            value={tier.max ?? ''}
                            placeholder="∞"
                            onChange={(e) => updateTier(index, 'max', e.target.value)}
                            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-gray-500">Pct</label>
                          <input
                            type="number"
                            step="0.01"
                            min={0}
                            max={1}
                            value={tier.pct}
                            onChange={(e) => updateTier(index, 'pct', e.target.value)}
                            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Activity Window (days)</label>
                    <input
                      type="number"
                      min={1}
                      value={config.tier_activity_window_days}
                      onChange={(e) => setConfig({ ...config, tier_activity_window_days: Number(e.target.value) })}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Step-down Max</label>
                    <input
                      type="number"
                      min={0}
                      value={config.tier_stepdown_max}
                      onChange={(e) => setConfig({ ...config, tier_stepdown_max: Number(e.target.value) })}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Inactivity Reset (days)</label>
                    <input
                      type="number"
                      min={1}
                      value={config.tier_inactivity_reset_days}
                      onChange={(e) => setConfig({ ...config, tier_inactivity_reset_days: Number(e.target.value) })}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Floor (Private In-Person) – cents</label>
                    <input
                      type="number"
                      min={0}
                      value={config.price_floor_cents.private_in_person}
                      onChange={(e) => updatePriceFloor('private_in_person', e.target.value)}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Floor (Private Remote) – cents</label>
                    <input
                      type="number"
                      min={0}
                      value={config.price_floor_cents.private_remote}
                      onChange={(e) => updatePriceFloor('private_remote', e.target.value)}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-5 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Cycle Length</label>
                    <input
                      type="number"
                      min={1}
                      value={config.student_credit_cycle.cycle_len}
                      onChange={(e) => updateCreditCycle('cycle_len', e.target.value)}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Mod 10</label>
                    <input
                      type="number"
                      min={0}
                      value={config.student_credit_cycle.mod10}
                      onChange={(e) => updateCreditCycle('mod10', e.target.value)}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">$10 Credit (cents)</label>
                    <input
                      type="number"
                      min={0}
                      value={config.student_credit_cycle.cents10}
                      onChange={(e) => updateCreditCycle('cents10', e.target.value)}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Mod 20</label>
                    <input
                      type="number"
                      min={0}
                      value={config.student_credit_cycle.mod20}
                      onChange={(e) => updateCreditCycle('mod20', e.target.value)}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">$20 Credit (cents)</label>
                    <input
                      type="number"
                      min={0}
                      value={config.student_credit_cycle.cents20}
                      onChange={(e) => updateCreditCycle('cents20', e.target.value)}
                      className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 focus:border-indigo-500 focus:ring-indigo-500"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="submit"
                    disabled={saving}
                    className="inline-flex items-center rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : 'Save Settings'}
                  </button>
                  {message && <span className="text-sm text-green-600 dark:text-green-400">{message}</span>}
                  {error && <span className="text-sm text-red-600 dark:text-red-400">{error}</span>}
                </div>
              </form>
            </div>

            <div className="bg-white/70 dark:bg-gray-900/40 backdrop-blur rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6">
              <h2 className="text-lg font-semibold mb-3">JSON Preview</h2>
              <pre className="whitespace-pre-wrap text-xs bg-gray-100 dark:bg-gray-800 rounded-lg p-4 overflow-x-auto">
                {jsonPreview}
              </pre>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
