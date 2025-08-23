'use client';

import { useEffect, useMemo, useState } from 'react';
import { publicApi } from '@/features/shared/api/client';
import { fetchWithAuth, API_ENDPOINTS, getErrorMessage } from '@/lib/api';
import type { CatalogService, ServiceCategory } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';

type AgeGroup = 'kids' | 'adults' | 'both';

type SelectedService = {
  catalog_service_id: string;
  name: string;
  hourly_rate: string; // keep as string for input control
  ageGroup: AgeGroup;
  description?: string;
  equipment?: string; // comma-separated freeform for UI
  levels_taught: Array<'beginner' | 'intermediate' | 'advanced'>;
  duration_options: number[];
  location_types: Array<'in-person' | 'online'>;
};

export default function Step3SkillsPricing() {
  const [categories, setCategories] = useState<ServiceCategory[]>([]);
  const [servicesByCategory, setServicesByCategory] = useState<Record<string, CatalogService[]>>({});
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedService[]>([]);
  const [requestText, setRequestText] = useState('');
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const [cats, all] = await Promise.all([
          publicApi.getServiceCategories(),
          publicApi.getAllServicesWithInstructors(),
        ]);

        if (cats.status === 200 && cats.data) {
          const filtered = cats.data.filter((c) => c.slug !== 'kids');
          setCategories(filtered);
          // collapse all by default
          const initialCollapsed: Record<string, boolean> = {};
          for (const c of filtered) initialCollapsed[c.slug] = true;
          setCollapsed(initialCollapsed);
        }
        if (all.status === 200 && all.data) {
          const map: Record<string, CatalogService[]> = {};
          for (const c of all.data.categories.filter((c: any) => c.slug !== 'kids')) {
            map[c.slug] = c.services;
          }
          setServicesByCategory(map);
        }
        // Load existing instructor profile to prefill selected services
        try {
          const meRes = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
          if (meRes.ok) {
            const me = await meRes.json();
            const mapped: SelectedService[] = (me.services || []).map((svc: any) => ({
              catalog_service_id: svc.service_catalog_id,
              name: svc.name || '',
              hourly_rate: String(svc.hourly_rate ?? ''),
              ageGroup:
                Array.isArray(svc.age_groups) && svc.age_groups.length === 2
                  ? 'both'
                  : (svc.age_groups || []).includes('kids')
                  ? 'kids'
                  : 'adults',
              description: svc.description || '',
              equipment: Array.isArray(svc.equipment_required) ? svc.equipment_required.join(', ') : '',
              levels_taught:
                Array.isArray(svc.levels_taught) && svc.levels_taught.length
                  ? svc.levels_taught
                  : ['beginner', 'intermediate', 'advanced'],
              duration_options: Array.isArray(svc.duration_options) && svc.duration_options.length ? svc.duration_options : [60],
              location_types:
                Array.isArray(svc.location_types) && svc.location_types.length
                  ? svc.location_types
                  : ['in-person'],
            }));
            if (mapped.length) setSelected(mapped);
          }
        } catch (e) {
          // ignore profile load errors; user may not be an instructor yet
        }
      } catch (e) {
        logger.error('Failed loading catalog', e);
        setError('Failed to load services');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const addService = (svc: CatalogService) => {
    if (selected.some((s) => s.catalog_service_id === svc.id)) return;
    setSelected((prev) => [
      ...prev,
      {
        catalog_service_id: svc.id,
        name: svc.name,
        hourly_rate: '',
        ageGroup: 'adults',
        description: '',
        equipment: '',
        levels_taught: ['beginner', 'intermediate', 'advanced'],
        duration_options: [60],
        location_types: ['in-person'],
      },
    ]);
  };

  const removeService = (id: string) => {
    setSelected((prev) => prev.filter((s) => s.catalog_service_id !== id));
  };

  const canSave = useMemo(() => {
    if (selected.length === 0) return true; // allow skip later
    return selected.every((s) => s.hourly_rate.trim().length > 0 && !Number.isNaN(Number(s.hourly_rate)));
  }, [selected]);

  const save = async () => {
    try {
      setSaving(true);
      setError(null);
      // PUT /instructors/me with services array
      const payload = {
        services: selected
          .filter((s) => s.hourly_rate.trim() !== '')
          .map((s) => ({
            service_catalog_id: s.catalog_service_id,
            hourly_rate: Number(s.hourly_rate),
            age_groups: s.ageGroup === 'both' ? ['kids', 'adults'] : [s.ageGroup],
            description: s.description && s.description.trim() ? s.description.trim() : undefined,
            duration_options: (s.duration_options && s.duration_options.length ? s.duration_options : [60]).sort((a, b) => a - b),
            levels_taught: s.levels_taught,
            equipment_required:
              s.equipment && s.equipment.trim()
                ? s.equipment
                    .split(',')
                    .map((x) => x.trim())
                    .filter((x) => x.length > 0)
                : undefined,
            location_types: s.location_types && s.location_types.length ? s.location_types : ['in-person'],
          })),
      };
      const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        setError(await getErrorMessage(res));
        return;
      }
      // Navigate to next step
      window.location.href = '/instructor/onboarding/step-4';
    } catch (e) {
      logger.error('Save services failed', e);
      setError('Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const submitServiceRequest = async () => {
    if (!requestText.trim()) return;
    try {
      setRequestSubmitting(true);
      setRequestSuccess(null);
      // Placeholder client-side submission. In future, wire to backend endpoint.
      // We simulate latency for UX consistency and log for observability.
      logger.info('Service request submitted', { requestText });
      await new Promise((resolve) => setTimeout(resolve, 600));
      setRequestSuccess("Thanks! We'll review and consider adding this skill.");
      setRequestText('');
    } catch (e) {
      setRequestSuccess('Something went wrong. Please try again.');
    } finally {
      setRequestSubmitting(false);
    }
  };

  if (loading) return <div className="p-8">Loading…</div>;

  return (
    <div className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-[#6A0DAD]">What do you teach?</h1>
      <p className="text-gray-600 mt-1">Select your skills and set your hourly rates</p>

      {error && <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">{error}</div>}

      <div className="mt-6 space-y-4">
        {categories.map((cat) => {
          const isCollapsed = collapsed[cat.slug] === true;
          return (
          <div key={cat.slug} className="rounded-2xl overflow-hidden shadow-sm ring-1 ring-gray-100">
            <button
              className="w-full px-4 py-3 flex items-center justify-between font-semibold tracking-wide text-gray-900 bg-[#D4B5F0]"
              onClick={() => setCollapsed((prev) => ({ ...prev, [cat.slug]: !isCollapsed }))}
            >
              <span>{cat.name}</span>
              <span className="text-sm">{isCollapsed ? '▼' : '▲'}</span>
            </button>
            {!isCollapsed && (
            <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {(servicesByCategory[cat.slug] || []).map((svc) => {
                const selectedFlag = selected.some((s) => s.catalog_service_id === svc.id);
                return (
                  <button
                    key={svc.id}
                    onClick={() => addService(svc)}
                    disabled={selectedFlag}
                    className={`px-4 py-3 text-sm text-gray-900 rounded-xl bg-white shadow-sm hover:shadow-md transition hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] ${selectedFlag ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    {svc.name} {selectedFlag ? '✓' : '+'}
                  </button>
                );
              })}
            </div>
            )}
          </div>
        );})}
      </div>

      {/* Global age group selector removed; per-service selection is below */}

      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900">Your selected skills</h2>
        {selected.length === 0 ? (
          <p className="text-gray-500 mt-2">You can add skills now or later.</p>
        ) : (
          <div className="mt-3 space-y-4 bg-gray-50 rounded-2xl p-4 ring-1 ring-gray-100">
            {selected.map((s) => (
              <div key={s.catalog_service_id} className="rounded-xl bg-white ring-1 ring-gray-200 p-4 shadow-sm">
                <div className="flex items-start justify-between">
                  <div className="text-gray-900 font-semibold">{s.name}</div>
                  <button
                    aria-label="Remove"
                    title="Remove"
                    className="ml-2 w-8 h-8 flex items-center justify-center rounded-full border border-gray-200 text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                    onClick={() => removeService(s.catalog_service_id)}
                  >
                    ×
                  </button>
                </div>
                <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <textarea
                    rows={2}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] bg-white"
                    placeholder="Brief description (optional)"
                    value={s.description || ''}
                    onChange={(e) =>
                      setSelected((prev) =>
                        prev.map((x) => (x.catalog_service_id === s.catalog_service_id ? { ...x, description: e.target.value } : x))
                      )
                    }
                  />
                  <textarea
                    rows={2}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] bg-white"
                    placeholder="Equipment required (comma-separated, optional)"
                    value={s.equipment || ''}
                    onChange={(e) =>
                      setSelected((prev) =>
                        prev.map((x) => (x.catalog_service_id === s.catalog_service_id ? { ...x, equipment: e.target.value } : x))
                      )
                    }
                  />
                </div>
                <div className="mt-3 flex items-center gap-2">
                  <span className="text-sm text-gray-600">Rate:</span>
                  <span className="text-gray-600">$</span>
                  <input
                    type="number"
                    min={1}
                    step="1"
                    inputMode="decimal"
                    className="w-28 rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] bg-white"
                    placeholder="75"
                    value={s.hourly_rate}
                    onChange={(e) =>
                      setSelected((prev) =>
                        prev.map((x) =>
                          x.catalog_service_id === s.catalog_service_id ? { ...x, hourly_rate: e.target.value } : x
                        )
                      )
                    }
                  />
                  <span className="text-gray-600">/hour</span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <span className="text-sm text-gray-600">Age group:</span>
                  <div className="inline-flex rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden">
                    {([
                      { key: 'kids', label: 'Kids' },
                      { key: 'adults', label: 'Adults' },
                      { key: 'both', label: 'Both' },
                    ] as const).map((opt) => (
                      <button
                        key={opt.key}
                        onClick={() =>
                          setSelected((prev) =>
                            prev.map((x) =>
                              x.catalog_service_id === s.catalog_service_id ? { ...x, ageGroup: opt.key } : x
                            )
                          )
                        }
                        className={`px-3 py-1.5 text-sm ${
                          s.ageGroup === opt.key ? 'bg-[#6A0DAD] text-white' : 'text-gray-700 hover:bg-gray-50'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <span className="text-sm text-gray-600">Levels:</span>
                  {(['beginner', 'intermediate', 'advanced'] as const).map((lvl) => (
                    <button
                      key={lvl}
                      onClick={() =>
                        setSelected((prev) =>
                          prev.map((x) =>
                            x.catalog_service_id === s.catalog_service_id
                              ? {
                                  ...x,
                                  levels_taught: x.levels_taught.includes(lvl)
                                    ? x.levels_taught.filter((v) => v !== lvl)
                                    : [...x.levels_taught, lvl],
                                }
                              : x
                          )
                        )
                      }
                      className={`px-3 py-1.5 rounded-full text-sm border ${
                        s.levels_taught.includes(lvl)
                          ? 'bg-[#6A0DAD] text-white border-[#6A0DAD]'
                          : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                      }`}
                      type="button"
                    >
                      {lvl[0].toUpperCase() + lvl.slice(1)}
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <span className="text-sm text-gray-600">Durations:</span>
                  {[30, 45, 60, 90].map((d) => (
                    <button
                      key={d}
                      onClick={() =>
                        setSelected((prev) =>
                          prev.map((x) =>
                            x.catalog_service_id === s.catalog_service_id
                              ? {
                                  ...x,
                                  duration_options: x.duration_options.includes(d)
                                    ? x.duration_options.filter((v) => v !== d)
                                    : [...x.duration_options, d],
                                }
                              : x
                          )
                        )
                      }
                      className={`px-3 py-1.5 rounded-full text-sm border ${
                        s.duration_options.includes(d)
                          ? 'bg-[#6A0DAD] text-white border-[#6A0DAD]'
                          : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                      }`}
                      type="button"
                    >
                      {d}m
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  <span className="text-sm text-gray-600">Location:</span>
                  {(['in-person', 'online'] as const).map((loc) => (
                    <button
                      key={loc}
                      onClick={() =>
                        setSelected((prev) =>
                          prev.map((x) =>
                            x.catalog_service_id === s.catalog_service_id
                              ? {
                                  ...x,
                                  location_types: x.location_types.includes(loc)
                                    ? x.location_types.filter((v) => v !== loc)
                                    : [...x.location_types, loc],
                                }
                              : x
                          )
                        )
                      }
                      className={`px-3 py-1.5 rounded-full text-sm border ${
                        s.location_types.includes(loc)
                          ? 'bg-[#6A0DAD] text-white border-[#6A0DAD]'
                          : 'bg-white text-gray-700 border-gray-200 hover:bg-gray-50'
                      }`}
                      type="button"
                    >
                      {loc === 'in-person' ? 'In‑person' : 'Online'}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Request a new service */}
      <div className="mt-8 rounded-2xl bg-[#D4B5F0] ring-1 ring-[#D4B5F0] p-5">
        <div className="text-gray-900 font-semibold">Don't see your skill? We'd love to add it!</div>
        <div className="mt-3 flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={requestText}
            onChange={(e) => setRequestText(e.target.value)}
            placeholder="Type your skill here..."
            className="flex-1 rounded-lg border border-gray-200 bg-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-white/70"
          />
          <button
            onClick={submitServiceRequest}
            disabled={!requestText.trim() || requestSubmitting}
            className="px-4 py-2 rounded-lg text-white bg-[#6A0DAD] hover:bg-[#5c0a9a] disabled:opacity-50 shadow-sm"
          >
            Submit request
          </button>
        </div>
        {requestSuccess && <div className="mt-2 text-sm text-gray-800">{requestSuccess}</div>}
      </div>

      <div className="mt-8 flex gap-3">
        <button
          onClick={save}
          disabled={!canSave || saving}
          className="px-5 py-2.5 rounded-lg text-white bg-[#6A0DAD] hover:bg-[#5c0a9a] disabled:opacity-50 shadow-sm"
        >
          {selected.length ? 'Save & Continue' : 'Add skills later →'}
        </button>
      </div>
    </div>
  );
}
