'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { AlertCircle } from 'lucide-react';

import AdminSidebar from '@/app/(admin)/admin/AdminSidebar';
import { useAdminAuth } from '@/hooks/useAdminAuth';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { withApiBase } from '@/lib/apiBase';
import { logger } from '@/lib/logger';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { toast } from 'sonner';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';

type TierConfig = components['schemas']['TierConfig'];
type PriceFloorConfig = components['schemas']['PriceFloorConfig'];
type StudentCreditCycle = components['schemas']['StudentCreditCycle'];
type PricingConfig = components['schemas']['PricingConfig'];
type PricingConfigPayload = components['schemas']['PricingConfigPayload'];
type PricingConfigResponse = components['schemas']['PricingConfigResponse'];

const DEFAULT_CONFIG: PricingConfig = {
  student_fee_pct: 0.12,
  founding_instructor_rate_pct: 0.08,
  founding_instructor_cap: 100,
  founding_search_boost: 1.5,
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

type LoadErrorKind = 'unauthorized' | 'notFound' | 'server' | 'unknown';

class PricingConfigError extends Error {
  constructor(public readonly kind: LoadErrorKind, message: string) {
    super(message);
    this.name = 'PricingConfigError';
  }
}

const LOAD_ERROR_COPY: Record<LoadErrorKind, { title: string; message: string; variant: 'destructive' | 'muted' | 'default' }> = {
  unauthorized: {
    title: 'Access restricted',
    message: "You don't have access to pricing settings.",
    variant: 'destructive',
  },
  notFound: {
    title: 'Endpoint unavailable',
    message: "Pricing endpoint isn't available.",
    variant: 'muted',
  },
  server: {
    title: 'Service issue',
    message: "Couldn't load settings. Please try again.",
    variant: 'destructive',
  },
  unknown: {
    title: 'Something went wrong',
    message: 'Could not load pricing settings.',
    variant: 'destructive',
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
  const [loadError, setLoadError] = useState<LoadErrorKind | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const initialConfigRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchConfig() {
      try {
        const response = await fetch(withApiBase('/api/v1/admin/config/pricing'), {
          credentials: 'include',
        });
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            throw new PricingConfigError('unauthorized', "You don't have access to pricing settings.");
          }
          if (response.status === 404) {
            throw new PricingConfigError('notFound', "Pricing endpoint isn't available.");
          }
          if (response.status >= 500) {
            throw new PricingConfigError('server', "Couldn't load settings. Please try again.");
          }
          throw new PricingConfigError('unknown', `Failed to fetch config (${response.status})`);
        }
        const responsePayload = (await response.json()) as PricingConfigResponse;
        if (!cancelled && responsePayload?.config) {
          setConfig(responsePayload.config);
          setUpdatedAt(responsePayload.updated_at ?? null);
          initialConfigRef.current = JSON.stringify(responsePayload.config);
          setLoadError(null);
          setSubmitError(null);
        }
      } catch (err) {
        if (process.env.NODE_ENV !== 'production') {
          logger.error('Failed to load pricing config', err as Error);
        }
        if (!cancelled) {
          if (err instanceof PricingConfigError) {
            setLoadError(err.kind);
          } else {
            setLoadError('unknown');
          }
          setSubmitError(null);
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

  const updateTier = (index: number, field: keyof TierConfig, value: string) => {
    setConfig((prev) => {
      const tiers = prev.instructor_tiers.map((tier, idx) => {
        if (idx !== index) return tier;
        if (field === 'max') {
          const trimmed = value.trim();
          return { ...tier, max: trimmed === '' ? null : Number(trimmed) };
        }
        const numeric = Number(value);
        if (Number.isNaN(numeric)) {
          return tier;
        }
        return { ...tier, [field]: numeric };
      });
      return { ...prev, instructor_tiers: tiers };
    });
  };

  const updatePriceFloor = (field: keyof PriceFloorConfig, value: string) => {
    const numeric = Number(value);
    setConfig((prev) => ({
      ...prev,
      price_floor_cents: {
        ...prev.price_floor_cents,
        [field]: Number.isNaN(numeric) ? prev.price_floor_cents[field] : numeric,
      },
    }));
  };

  const updateCreditCycle = (field: keyof StudentCreditCycle, value: string) => {
    const numeric = Number(value);
    setConfig((prev) => ({
      ...prev,
      student_credit_cycle: {
        ...prev.student_credit_cycle,
        [field]: Number.isNaN(numeric) ? prev.student_credit_cycle[field] : numeric,
      },
    }));
  };

  const updateFoundingConfig = (
    field: 'founding_instructor_rate_pct' | 'founding_instructor_cap' | 'founding_search_boost',
    value: string,
  ) => {
    const numeric = Number(value);
    setConfig((prev) => ({
      ...prev,
      [field]: Number.isNaN(numeric) ? prev[field] : numeric,
    }));
  };

  const configSnapshot = useMemo(() => JSON.stringify(config), [config]);
  const isDirty = Boolean(initialConfigRef.current && initialConfigRef.current !== configSnapshot);

  const validation = useMemo(() => {
    const tierErrors = config.instructor_tiers.map((tier) => {
      const pctValid = Number.isFinite(tier.pct) && tier.pct >= 0 && tier.pct <= 1;
      const minValid = Number.isFinite(tier.min) && tier.min >= 0;
      const maxValid =
        tier.max === null || tier.max === undefined
          ? true
          : Number.isFinite(tier.max) && tier.max >= tier.min;
      return {
        pct: pctValid ? null : 'Enter a decimal between 0 and 1.',
        min: minValid ? null : 'Must be a non-negative integer.',
        max: maxValid ? null : 'Must be greater than or equal to Min, or leave empty.',
      };
    });

    const studentFeeValid =
      Number.isFinite(config.student_fee_pct) && config.student_fee_pct >= 0 && config.student_fee_pct <= 1;

    const foundingRateValid =
      Number.isFinite(config.founding_instructor_rate_pct) &&
      config.founding_instructor_rate_pct >= 0 &&
      config.founding_instructor_rate_pct <= 1;
    const foundingCapValid =
      Number.isFinite(config.founding_instructor_cap) && config.founding_instructor_cap >= 1;
    const foundingBoostValid =
      Number.isFinite(config.founding_search_boost) &&
      config.founding_search_boost >= 1 &&
      config.founding_search_boost <= 3;

    const floorsValid =
      config.price_floor_cents.private_in_person >= 0 &&
      config.price_floor_cents.private_remote >= 0;

    const credit = config.student_credit_cycle;
    const creditErrors = {
      cycle_len: credit.cycle_len > 0 ? null : 'Must be greater than zero.',
      mod10: credit.mod10 >= 0 ? null : 'Must be non-negative.',
      cents10: credit.cents10 >= 0 ? null : 'Must be non-negative.',
      mod20: credit.mod20 >= 0 ? null : 'Must be non-negative.',
      cents20: credit.cents20 >= 0 ? null : 'Must be non-negative.',
    };

    const tierWindowValid = config.tier_activity_window_days > 0;
    const tierStepdownValid = config.tier_stepdown_max >= 0;
    const inactivityValid = config.tier_inactivity_reset_days > 0;

    const hasTierErrors = tierErrors.some((entry) => entry.pct || entry.min || entry.max);
    const hasCreditErrors = Object.values(creditErrors).some(Boolean);

    const hasErrors =
      !studentFeeValid ||
      !foundingRateValid ||
      !foundingCapValid ||
      !foundingBoostValid ||
      hasTierErrors ||
      !floorsValid ||
      hasCreditErrors ||
      !tierWindowValid ||
      !tierStepdownValid ||
      !inactivityValid;

    return {
      errors: {
        studentFee: studentFeeValid ? null : 'Enter a decimal between 0 and 1.',
        foundingRate: foundingRateValid ? null : 'Enter a decimal between 0 and 1.',
        foundingCap: foundingCapValid ? null : 'Must be at least 1.',
        foundingBoost: foundingBoostValid ? null : 'Enter a decimal between 1 and 3.',
        tiers: tierErrors,
        floors: floorsValid ? null : 'Floors must be non-negative.',
        credit: creditErrors,
        tierWindow: tierWindowValid ? null : 'Must be greater than zero.',
        tierStepdown: tierStepdownValid ? null : 'Must be non-negative.',
        inactivity: inactivityValid ? null : 'Must be greater than zero.',
      },
      hasErrors,
    };
  }, [config]);

  const canSubmit = isDirty && !validation.hasErrors && !saving;

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setSubmitError(null);
    try {
      const configPayload: PricingConfigPayload = config;
      const response = await fetch(withApiBase('/api/v1/admin/config/pricing'), {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configPayload),
      });

      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => null)) as ApiErrorResponse | null;
        const detail = errorPayload?.detail ?? errorPayload?.message ?? `HTTP ${response.status}`;
        throw new Error(String(detail));
      }

      const responsePayload = (await response.json()) as PricingConfigResponse;
      setConfig(responsePayload.config);
      setUpdatedAt(responsePayload.updated_at ?? null);
      initialConfigRef.current = JSON.stringify(responsePayload.config);
      toast.success('Pricing configuration saved');
    } catch (err) {
      if (process.env.NODE_ENV !== 'production') {
        logger.error('Failed to save pricing config', err as Error);
      }
      setSubmitError((err as Error).message || 'Failed to save pricing configuration');
    } finally {
      setSaving(false);
    }
  };

  if (isLoading || loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center">
                <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">
                  iNSTAiNSTRU
                </Link>
                <Skeleton className="h-6 w-48 rounded-full" />
              </div>
              <Skeleton className="h-9 w-24 rounded-full" />
            </div>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-12 gap-6">
            <aside className="col-span-12 md:col-span-3 lg:col-span-3">
              <Skeleton className="h-[480px] w-full rounded-xl" />
            </aside>
            <section className="col-span-12 md:col-span-9 lg:col-span-9">
              <div className="rounded-2xl bg-white/60 dark:bg-gray-900/40 backdrop-blur shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6">
                <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="space-y-2">
                    <Skeleton className="h-6 w-56" />
                    <Skeleton className="h-4 w-64" />
                  </div>
                  <Skeleton className="h-4 w-32" />
                </div>
                <div className="space-y-6">
                  <Skeleton className="h-10 w-full rounded" />
                  <Separator className="my-4 bg-muted/30" />
                  <Skeleton className="h-28 w-full rounded" />
                  <Separator className="my-4 bg-muted/30" />
                  <Skeleton className="h-24 w-full rounded" />
                </div>
                <div className="mt-6 flex justify-end">
                  <Skeleton className="h-9 w-32 rounded-full" />
                </div>
              </div>
            </section>
          </div>
        </main>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-6">
        <div className="text-center text-sm text-muted-foreground">You do not have access to this page.</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header className="border-b border-gray-200/70 dark:border-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-semibold text-indigo-600 dark:text-indigo-400 mr-8">
                iNSTAiNSTRU
              </Link>
              <h1 className="text-xl font-semibold">Pricing Settings</h1>
            </div>
            <div className="flex items-center space-x-3">
              <button onClick={logout} className="inline-flex items-center rounded-full px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 ring-1 ring-gray-300/70 dark:ring-gray-700/60 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 cursor-pointer">
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

          <section className="col-span-12 md:col-span-9 lg:col-span-9">
            <div className="rounded-2xl bg-white/60 dark:bg-gray-900/40 backdrop-blur shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 p-6">
              <div className="mb-6 space-y-1 sm:flex sm:items-start sm:justify-between sm:space-y-0">
                <div>
                  <h2 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">Pricing Configuration</h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    Configure booking fees, instructor tiers, and credit milestones.
                  </p>
                </div>
                <span className="text-xs text-gray-600 dark:text-gray-400 sm:ml-auto">Last updated: {formatTimestamp(updatedAt)}</span>
              </div>

              <form onSubmit={handleSubmit}>
                <div className="space-y-8">
                  {loadError && !isDirty ? (
                    <Alert variant={LOAD_ERROR_COPY[loadError].variant} className="border-border/50">
                      <AlertCircle className="h-4 w-4" aria-hidden="true" />
                      <AlertTitle>{LOAD_ERROR_COPY[loadError].title}</AlertTitle>
                      <AlertDescription>{LOAD_ERROR_COPY[loadError].message}</AlertDescription>
                    </Alert>
                  ) : null}

                  {submitError ? (
                    <Alert variant="destructive" className="border-border/50">
                      <AlertCircle className="h-4 w-4" aria-hidden="true" />
                      <AlertTitle>Save failed</AlertTitle>
                      <AlertDescription>{submitError}</AlertDescription>
                    </Alert>
                  ) : null}

                  <section className="space-y-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Student Booking Protection Fee</h3>
                      <p className="text-xs text-muted-foreground">Enter a decimal between 0 and 1 (0.12 = 12%).</p>
                    </div>
                    <div className="grid grid-cols-12 gap-4">
                      <div className="col-span-12 sm:col-span-4">
                        <Label htmlFor="student-fee" className="text-sm font-medium text-foreground">
                          Protection fee
                        </Label>
                        <div className="mt-1 flex items-center">
                          <input
                            id="student-fee"
                            type="number"
                            step="0.01"
                            min={0}
                            max={1}
                            value={config.student_fee_pct}
                            onChange={(e) => setConfig({ ...config, student_fee_pct: Number(e.target.value) })}
                            className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                          />
                          <Badge variant="secondary" className="ml-2 text-[11px] px-1.5">
                            decimal
                          </Badge>
                        </div>
                        {validation.errors.studentFee ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.studentFee}</p>
                        ) : null}
                      </div>
                    </div>
                  </section>

                  <Separator className="my-6 bg-muted/30" />

                  <section className="space-y-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Instructor Tiers</h3>
                      <p className="text-xs text-muted-foreground">Percentages are decimals (0.15 = 15%). Leave Max blank for no upper bound.</p>
                    </div>
                    <div className="space-y-4">
                      {config.instructor_tiers.map((tier, index) => {
                        const errors =
                          validation.errors.tiers[index] ?? {
                            min: null,
                            max: null,
                            pct: null,
                          };
                        return (
                          <div key={`tier-${index}`} className="grid grid-cols-12 gap-4">
                            <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-2">
                              <Label htmlFor={`tier-${index}-min`} className="text-sm font-medium text-foreground">
                                Min sessions
                              </Label>
                              <input
                                id={`tier-${index}-min`}
                                type="number"
                                min={0}
                                value={tier.min}
                                onChange={(e) => updateTier(index, 'min', e.target.value)}
                                className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                              />
                              {errors.min ? <p className="mt-1 text-xs text-destructive">{errors.min}</p> : null}
                            </div>
                            <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-2">
                              <Label htmlFor={`tier-${index}-max`} className="text-sm font-medium text-foreground">
                                Max sessions
                              </Label>
                              <input
                                id={`tier-${index}-max`}
                                type="number"
                                min={tier.min}
                                value={tier.max ?? ''}
                                placeholder="∞"
                                onChange={(e) => updateTier(index, 'max', e.target.value)}
                                className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                              />
                              {errors.max ? <p className="mt-1 text-xs text-destructive">{errors.max}</p> : null}
                            </div>
                            <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-3">
                              <Label htmlFor={`tier-${index}-pct`} className="text-sm font-medium text-foreground">
                                Commission pct
                              </Label>
                              <div className="mt-1 flex items-center gap-2">
                                <input
                                  id={`tier-${index}-pct`}
                                  type="number"
                                  step="0.01"
                                  min={0}
                                  max={1}
                                  value={tier.pct}
                                  onChange={(e) => updateTier(index, 'pct', e.target.value)}
                                  className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                                />
                                <Badge variant="secondary" className="shrink-0 px-1.5 text-[11px]">
                                  decimal
                                </Badge>
                              </div>
                              {errors.pct ? <p className="mt-1 text-xs text-destructive">{errors.pct}</p> : null}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>

                  <Separator className="my-6 bg-muted/30" />

                  <section className="space-y-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Tier maintenance</h3>
                      <p className="text-xs text-muted-foreground">Controls rolling activity window, demotion limits, and inactivity resets.</p>
                    </div>
                    <div className="grid grid-cols-12 gap-4">
                      <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-3">
                        <Label htmlFor="tier-activity-window" className="text-sm font-medium text-foreground">
                          Activity window (days)
                        </Label>
                        <input
                          id="tier-activity-window"
                          type="number"
                          min={1}
                          value={config.tier_activity_window_days}
                          onChange={(e) => setConfig({ ...config, tier_activity_window_days: Number(e.target.value) })}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        {validation.errors.tierWindow ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.tierWindow}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-3">
                        <Label htmlFor="tier-stepdown" className="text-sm font-medium text-foreground">
                          Step-down max
                        </Label>
                        <input
                          id="tier-stepdown"
                          type="number"
                          min={0}
                          value={config.tier_stepdown_max}
                          onChange={(e) => setConfig({ ...config, tier_stepdown_max: Number(e.target.value) })}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        {validation.errors.tierStepdown ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.tierStepdown}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-3">
                        <Label htmlFor="tier-inactivity" className="text-sm font-medium text-foreground">
                          Inactivity reset (days)
                        </Label>
                        <input
                          id="tier-inactivity"
                          type="number"
                          min={1}
                          value={config.tier_inactivity_reset_days}
                          onChange={(e) => setConfig({ ...config, tier_inactivity_reset_days: Number(e.target.value) })}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        {validation.errors.inactivity ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.inactivity}</p>
                        ) : null}
                      </div>
                    </div>
                  </section>

                  <Separator className="my-6 bg-muted/30" />

                  <section className="space-y-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Founding Instructor Program</h3>
                      <p className="text-xs text-muted-foreground">
                        Settings for founding instructors who receive special lifetime benefits.
                      </p>
                    </div>
                    <div className="grid grid-cols-12 gap-4">
                      <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-3">
                        <Label htmlFor="founding-rate" className="text-sm font-medium text-foreground">
                          Founding rate
                        </Label>
                        <div className="mt-1 flex items-center gap-2">
                          <input
                            id="founding-rate"
                            type="number"
                            step="0.01"
                            min={0}
                            max={1}
                            value={config.founding_instructor_rate_pct}
                            onChange={(e) => updateFoundingConfig('founding_instructor_rate_pct', e.target.value)}
                            className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                          />
                          <Badge variant="secondary" className="shrink-0 px-1.5 text-[11px]">
                            decimal
                          </Badge>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">0.08 = 8%</p>
                        {validation.errors.foundingRate ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.foundingRate}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-3">
                        <Label htmlFor="founding-cap" className="text-sm font-medium text-foreground">
                          Founding cap
                        </Label>
                        <input
                          id="founding-cap"
                          type="number"
                          min={1}
                          value={config.founding_instructor_cap}
                          onChange={(e) => updateFoundingConfig('founding_instructor_cap', e.target.value)}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        <p className="mt-1 text-xs text-muted-foreground">Max founding instructors</p>
                        {validation.errors.foundingCap ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.foundingCap}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-6 md:col-span-4 xl:col-span-3">
                        <Label htmlFor="founding-boost" className="text-sm font-medium text-foreground">
                          Search boost
                        </Label>
                        <input
                          id="founding-boost"
                          type="number"
                          step="0.1"
                          min={1}
                          max={3}
                          value={config.founding_search_boost}
                          onChange={(e) => updateFoundingConfig('founding_search_boost', e.target.value)}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        <p className="mt-1 text-xs text-muted-foreground">Ranking multiplier (1.0-3.0)</p>
                        {validation.errors.foundingBoost ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.foundingBoost}</p>
                        ) : null}
                      </div>
                    </div>
                  </section>

                  <Separator className="my-6 bg-muted/30" />

                  <section className="space-y-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Price floors (private sessions)</h3>
                      <p className="text-xs text-muted-foreground">Floors are 60-minute baselines; shorter or longer durations are pro-rated.</p>
                    </div>
                    <div className="grid grid-cols-12 gap-4">
                      <div className="col-span-12 sm:col-span-6 lg:col-span-4 xl:col-span-3">
                        <Label htmlFor="price-floor-in-person" className="text-sm font-medium text-foreground">
                          In-person floor
                        </Label>
                        <div className="mt-1 flex items-center">
                          <input
                            id="price-floor-in-person"
                            type="number"
                            min={0}
                            value={config.price_floor_cents.private_in_person}
                            onChange={(e) => updatePriceFloor('private_in_person', e.target.value)}
                            className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                          />
                          <Badge variant="secondary" className="ml-2 text-[11px] px-1.5">
                            cents
                          </Badge>
                        </div>
                      </div>
                      <div className="col-span-12 sm:col-span-6 lg:col-span-4 xl:col-span-3">
                        <Label htmlFor="price-floor-remote" className="text-sm font-medium text-foreground">
                          Remote floor
                        </Label>
                        <div className="mt-1 flex items-center">
                          <input
                            id="price-floor-remote"
                            type="number"
                            min={0}
                            value={config.price_floor_cents.private_remote}
                            onChange={(e) => updatePriceFloor('private_remote', e.target.value)}
                            className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                          />
                          <Badge variant="secondary" className="ml-2 text-[11px] px-1.5">
                            cents
                          </Badge>
                        </div>
                      </div>
                    </div>
                    {validation.errors.floors ? (
                      <p className="text-xs text-destructive">{validation.errors.floors}</p>
                    ) : null}
                  </section>

                  <Separator className="my-6 bg-muted/30" />

                  <section className="space-y-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Student credit milestones</h3>
                      <p className="text-xs text-muted-foreground">Define when $10/$20 credits unlock within the session cycle.</p>
                    </div>
                    <div className="grid grid-cols-12 gap-4">
                      <div className="col-span-12 sm:col-span-3">
                        <Label htmlFor="credit-cycle-len" className="text-sm font-medium text-foreground">
                          Cycle length
                        </Label>
                        <input
                          id="credit-cycle-len"
                          type="number"
                          min={1}
                          value={config.student_credit_cycle.cycle_len}
                          onChange={(e) => updateCreditCycle('cycle_len', e.target.value)}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        {validation.errors.credit.cycle_len ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.credit.cycle_len}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-2">
                        <Label htmlFor="credit-mod-10" className="text-sm font-medium text-foreground">
                          Mod 10
                        </Label>
                        <input
                          id="credit-mod-10"
                          type="number"
                          min={0}
                          value={config.student_credit_cycle.mod10}
                          onChange={(e) => updateCreditCycle('mod10', e.target.value)}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        {validation.errors.credit.mod10 ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.credit.mod10}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-3">
                        <Label htmlFor="credit-cents-10" className="text-sm font-medium text-foreground">
                          $10 credit
                        </Label>
                        <div className="mt-1 flex items-center">
                          <input
                            id="credit-cents-10"
                            type="number"
                            min={0}
                            value={config.student_credit_cycle.cents10}
                            onChange={(e) => updateCreditCycle('cents10', e.target.value)}
                            className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                          />
                          <Badge variant="secondary" className="ml-2 text-[11px] px-1.5">
                            cents
                          </Badge>
                        </div>
                        {validation.errors.credit.cents10 ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.credit.cents10}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-2">
                        <Label htmlFor="credit-mod-20" className="text-sm font-medium text-foreground">
                          Mod 20
                        </Label>
                        <input
                          id="credit-mod-20"
                          type="number"
                          min={0}
                          value={config.student_credit_cycle.mod20}
                          onChange={(e) => updateCreditCycle('mod20', e.target.value)}
                          className="mt-1 w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                        />
                        {validation.errors.credit.mod20 ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.credit.mod20}</p>
                        ) : null}
                      </div>
                      <div className="col-span-12 sm:col-span-2">
                        <Label htmlFor="credit-cents-20" className="text-sm font-medium text-foreground">
                          $20 credit
                        </Label>
                        <div className="mt-1 flex items-center">
                          <input
                            id="credit-cents-20"
                            type="number"
                            min={0}
                            value={config.student_credit_cycle.cents20}
                            onChange={(e) => updateCreditCycle('cents20', e.target.value)}
                            className="w-full rounded-lg px-3 py-2 text-sm ring-1 ring-gray-300/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/70"
                          />
                          <Badge variant="secondary" className="ml-2 text-[11px] px-1.5">
                            cents
                          </Badge>
                        </div>
                        {validation.errors.credit.cents20 ? (
                          <p className="mt-1 text-xs text-destructive">{validation.errors.credit.cents20}</p>
                        ) : null}
                      </div>
                    </div>
                  </section>

                  <Separator className="my-6 bg-muted/30" />

                  <section className="space-y-2">
                    <h3 className="text-sm font-medium text-foreground">JSON preview</h3>
                    <pre className="whitespace-pre-wrap text-xs bg-muted/20 rounded-lg p-4 overflow-x-auto">
                      {JSON.stringify(config, null, 2)}
                    </pre>
                  </section>
                </div>

                <div className="mt-6 flex items-center justify-end gap-3">
                  <button
                    type="submit"
                    disabled={!canSubmit}
                    className="px-4 py-2 rounded-md bg-indigo-600 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed ml-auto"
                  >
                    {saving ? 'Saving…' : 'Save settings'}
                  </button>
                </div>
              </form>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
