'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { fetchWithAuth, API_ENDPOINTS, getErrorMessage } from '@/lib/api';
import { logger } from '@/lib/logger';

type Profile = {
  bio: string;
  areas_of_service: string[];
  years_experience: number;
  min_advance_booking_hours?: number;
  buffer_time_minutes?: number;
};

type ServiceAreaItem = { id: string; neighborhood_id?: string; ntacode?: string | null; name?: string | null; borough?: string | null };
type ServiceAreasResponse = { items: ServiceAreaItem[]; total: number };
type NYCZipCheck = { is_nyc: boolean; borough?: string | null };

export default function InstructorProfileSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>({ bio: '', areas_of_service: [], years_experience: 0 });
  const [areaInput, setAreaInput] = useState('');
  const [isNYC, setIsNYC] = useState<boolean>(true); // default to true for now
  const [selectedNeighborhoods, setSelectedNeighborhoods] = useState<Set<string>>(new Set());
  const [boroughOpen, setBoroughOpen] = useState<string | null>(null);
  const [boroughNeighborhoods, setBoroughNeighborhoods] = useState<Record<string, ServiceAreaItem[]>>({});
  const [boroughFilter, setBoroughFilter] = useState<string>('');
  const [idToItem, setIdToItem] = useState<Record<string, ServiceAreaItem>>({});

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const res = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
        if (!res.ok) {
          setError(await getErrorMessage(res));
          return;
        }
        const data = await res.json();
        setProfile({
          bio: data.bio || '',
          areas_of_service: Array.isArray(data.areas_of_service)
            ? data.areas_of_service
            : (data.areas_of_service || '').split(',').map((x: string) => x.trim()).filter((x: string) => x.length),
          years_experience: data.years_experience ?? 0,
          min_advance_booking_hours: data.min_advance_booking_hours ?? 2,
          buffer_time_minutes: data.buffer_time_minutes ?? 0,
        });

        // Prefill service areas (neighborhoods)
        try {
          const areasRes = await fetchWithAuth('/api/addresses/service-areas/me');
          if (areasRes.ok) {
            const areas: ServiceAreasResponse = await areasRes.json();
            const items = (areas.items || []) as ServiceAreaItem[];
            const ids = items
              .map((a) => a.neighborhood_id || (a as any).id)
              .filter((v: string | undefined): v is string => typeof v === 'string');
            setSelectedNeighborhoods(new Set(ids));
            // Prime name map so selections show even before a borough loads
            setIdToItem((prev) => {
              const next = { ...prev } as Record<string, ServiceAreaItem>;
              for (const a of items) {
                const nid = a.neighborhood_id || (a as any).id;
                if (nid) next[nid] = a;
              }
              return next;
            });
          }
        } catch {}

        // Detect NYC from default address postal code if available
        try {
          const addrRes = await fetchWithAuth('/api/addresses/me');
          if (addrRes.ok) {
            const list = await addrRes.json();
            const def = (list.items || []).find((a: any) => a.is_default) || (list.items || [])[0];
            const zip = def?.postal_code;
            if (zip) {
              const nycRes = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${API_ENDPOINTS.NYC_ZIP_CHECK}?zip=${encodeURIComponent(zip)}`);
              if (nycRes.ok) {
                const nyc: NYCZipCheck = await nycRes.json();
                setIsNYC(!!nyc.is_nyc);
              }
            }
          }
        } catch {}
      } catch (e) {
        logger.error('Failed to load profile', e);
        setError('Failed to load profile');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const canSave = useMemo(() => {
    return profile.bio.trim().length >= 1 && profile.areas_of_service.length >= 1;
  }, [profile]);

  const addArea = () => {
    const val = areaInput.trim();
    if (!val) return;
    setProfile((p) => ({ ...p, areas_of_service: Array.from(new Set([...(p.areas_of_service || []), toTitle(val)])) }));
    setAreaInput('');
  };
  const removeArea = (area: string) => {
    setProfile((p) => ({ ...p, areas_of_service: (p.areas_of_service || []).filter((a) => a !== area) }));
  };

  const save = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);
      const payload = {
        bio: profile.bio.trim(),
        areas_of_service: profile.areas_of_service,
        years_experience: Number(profile.years_experience) || 0,
        min_advance_booking_hours: profile.min_advance_booking_hours ?? 2,
        buffer_time_minutes: profile.buffer_time_minutes ?? 0,
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

      // Persist service areas
      try {
        await fetchWithAuth('/api/addresses/service-areas/me', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ neighborhood_ids: Array.from(selectedNeighborhoods) }),
        });
      } catch {}

      setSuccess('Profile saved');
    } catch (e) {
      setError('Failed to save profile');
    } finally {
      setSaving(false);
    }
  };

  // NYC helpers
  const NYC_BOROUGHS = ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const;

  const loadBoroughNeighborhoods = async (borough: string) => {
    if (boroughNeighborhoods[borough]) return;
    try {
      const url = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/addresses/regions/neighborhoods?region_type=nyc&borough=${encodeURIComponent(borough)}&per_page=500`;
      const r = await fetch(url);
      if (r.ok) {
        const data = await r.json();
        const list = (data.items || []) as ServiceAreaItem[];
        setBoroughNeighborhoods((prev) => ({ ...prev, [borough]: list }));
        // Update id->item map for display in the selection panel
        setIdToItem((prev) => {
          const next = { ...prev } as Record<string, ServiceAreaItem>;
          for (const it of list) {
            const nid = it.neighborhood_id || (it as any).id;
            if (nid) next[nid] = it;
          }
          return next;
        });
      }
    } catch {}
  };

  const toggleBoroughAll = (borough: string, value: boolean) => {
    const items = boroughNeighborhoods[borough] || [];
    const ids = items.map((i) => i.neighborhood_id || (i as any).id);
    setSelectedNeighborhoods((prev) => {
      const next = new Set(prev);
      if (value) {
        ids.forEach((id) => next.add(id));
      } else {
        ids.forEach((id) => next.delete(id));
      }
      return next;
    });
  };

  const toggleNeighborhood = (id: string) => {
    setSelectedNeighborhoods((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Compute borough selection status for indeterminate styling
  const getBoroughCounts = (borough: string) => {
    const list = boroughNeighborhoods[borough] || [];
    const ids = list.map((n) => n.neighborhood_id || (n as any).id).filter(Boolean) as string[];
    let selected = 0;
    if (ids.length) {
      for (const id of ids) if (selectedNeighborhoods.has(id)) selected++;
    } else {
      // Fallback: count by idToItem when list not loaded
      for (const id of selectedNeighborhoods) if (idToItem[id]?.borough === borough) selected++;
    }
    return { selected, total: ids.length };
  };

  if (loading) return <div className="p-8">Loading…</div>;

  return (
    <div className="max-w-5xl mx-auto p-6">
      <h1 className="text-2xl font-semibold text-[#6A0DAD]">Profile Settings</h1>
      <p className="text-gray-600 mt-1">Edit your public profile details here.</p>

      <div className="mt-6">
        <Link href="/instructor/dashboard" className="text-purple-700 hover:underline">Back to dashboard</Link>
      </div>

      {error && <div className="mt-4 rounded-md bg-red-50 text-red-700 px-4 py-2">{error}</div>}
      {success && <div className="mt-4 rounded-md bg-green-50 text-green-700 px-4 py-2">{success}</div>}

      <div className="mt-6 space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700">Bio</label>
          <textarea
            rows={4}
            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] bg-white"
            placeholder="Tell students about your experience, style, and approach"
            value={profile.bio}
            onChange={(e) => setProfile((p) => ({ ...p, bio: e.target.value }))}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Areas you serve</label>
          {isNYC ? (
            <div className="mt-2 space-y-3">
              <div className="flex flex-wrap gap-2">
                {NYC_BOROUGHS.map((b) => {
                  const { selected, total } = getBoroughCounts(b);
                  const isAll = total > 0 && selected > 0 && selected === total;
                  const isSome = selected > 0 && (!total || selected < total);
                  const base = 'px-3 py-1.5 rounded-full text-sm border';
                  const open = boroughOpen === b;
                  const cls = isAll
                    ? `${base} bg-[#6A0DAD] text-white border-[#6A0DAD]`
                    : isSome
                    ? `${base} bg-[#F6ECFF] text-[#6A0DAD] border-[#D4B5F0]`
                    : `${base} bg-white text-gray-700 border-gray-200 hover:bg-gray-50`;
                  const openRing = open ? ' ring-2 ring-[#D4B5F0]' : '';
                  return (
                    <button
                      key={b}
                      onClick={async () => {
                        setBoroughOpen(boroughOpen === b ? null : b);
                        await loadBoroughNeighborhoods(b);
                      }}
                      type="button"
                      className={cls + openRing}
                    >
                      {b}
                      {selected > 0 && (
                        <span
                          className={`ml-2 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full px-1.5 text-xs ${
                            isAll
                              ? 'bg-white text-[#6A0DAD] ring-1 ring-white/60'
                              : 'bg-[#F3E8FF] text-[#6A0DAD] ring-1 ring-[#D4B5F0]'
                          }`}
                        >
                          {selected}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
              {/* Global selection panel (persists across boroughs) */}
              {selectedNeighborhoods.size > 0 && (
                <div className="mt-3 rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                  <div className="text-sm text-gray-700 mb-2">Selected neighborhoods</div>
                  <div className="flex flex-wrap gap-2">
                    {Array.from(selectedNeighborhoods).map((id) => {
                      const it = idToItem[id];
                      const label = it?.name || id;
                      const hint = it?.borough ? ` • ${it.borough}` : '';
                      return (
                        <span key={id} className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-[#F9FAFB] px-3 py-1 text-sm text-gray-800">
                          {label}
                          <span className="text-gray-500">{hint}</span>
                          <button
                            className="w-5 h-5 flex items-center justify-center rounded-full border border-gray-200 text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                            onClick={() => toggleNeighborhood(id)}
                            aria-label={`Remove ${label}`}
                          >
                            ×
                          </button>
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
              {boroughOpen && (
                <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div className="font-medium text-gray-900">{boroughOpen}</div>
                    <div className="flex gap-2">
                      <button
                        className="text-sm px-3 py-1 rounded-md ring-1 ring-gray-200 hover:bg-gray-50"
                        onClick={() => toggleBoroughAll(boroughOpen!, true)}
                      >
                        Select all
                      </button>
                      <button
                        className="text-sm px-3 py-1 rounded-md ring-1 ring-gray-200 hover:bg-gray-50"
                        onClick={() => toggleBoroughAll(boroughOpen!, false)}
                      >
                        Clear all
                      </button>
                    </div>
                  </div>
                  <div className="mt-3">
                    <input
                      type="text"
                      value={boroughFilter}
                      onChange={(e) => setBoroughFilter(e.target.value)}
                      placeholder="Search neighborhoods..."
                      className="w-full rounded-md border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
                    />
                  </div>
                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 max-h-80 overflow-auto">
                    {(boroughNeighborhoods[boroughOpen] || [])
                      .filter((n) => (n.name || '').toLowerCase().includes(boroughFilter.toLowerCase()))
                      .map((n) => {
                        const nid = n.neighborhood_id || (n as any).id;
                        const checked = selectedNeighborhoods.has(nid);
                        return (
                          <label key={nid} className={`cursor-pointer flex items-center gap-2 text-sm rounded-lg border px-3 py-2 ${checked ? 'bg-[#F3E8FF] border-[#D4B5F0]' : 'bg-white border-gray-200 hover:bg-gray-50'}`}>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleNeighborhood(nid)}
                            />
                            <span>{n.name || nid}</span>
                          </label>
                        );
                      })}
                  </div>
                </div>
              )}

              {/* Summary */}
              <div className="text-sm text-gray-600">
                Selected neighborhoods: {selectedNeighborhoods.size}
              </div>
            </div>
          ) : (
            <div className="mt-2 rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-600">
              Your city is not yet supported for granular neighborhoods. We’ll add it soon.
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Years of experience</label>
            <input
              type="number"
              min={0}
              max={50}
              value={profile.years_experience}
              onChange={(e) => setProfile((p) => ({ ...p, years_experience: Number(e.target.value || 0) }))}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] bg-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Min advance notice (hours)</label>
            <input
              type="number"
              min={0}
              max={168}
              value={profile.min_advance_booking_hours ?? 2}
              onChange={(e) => setProfile((p) => ({ ...p, min_advance_booking_hours: Number(e.target.value || 0) }))}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] bg-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Buffer between lessons (minutes)</label>
            <input
              type="number"
              min={0}
              max={60}
              value={profile.buffer_time_minutes ?? 0}
              onChange={(e) => setProfile((p) => ({ ...p, buffer_time_minutes: Number(e.target.value || 0) }))}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] bg-white"
            />
          </div>
        </div>

        <div className="pt-2">
          <button
            onClick={save}
            disabled={!canSave || saving}
            className="px-5 py-2.5 rounded-lg text-white bg-[#6A0DAD] hover:bg-[#5c0a9a] disabled:opacity-50 shadow-sm"
          >
            Save profile
          </button>
        </div>
      </div>
    </div>
  );
}

function toTitle(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ');
}
