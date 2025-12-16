// frontend/app/(admin)/admin/location-learning/CreateAliasModal.tsx
'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { fetchWithAuth } from '@/lib/api';

interface RegionOption {
  id: string;
  name: string;
  borough?: string | null;
}

interface RegionsResponse {
  regions: RegionOption[];
}

async function fetchRegions(): Promise<RegionsResponse> {
  const res = await fetchWithAuth('/api/v1/admin/location-learning/regions?limit=5000');
  if (!res.ok) throw new Error('Failed to fetch regions');
  return res.json() as Promise<RegionsResponse>;
}

function normalizeText(value: string): string {
  return value.trim().toLowerCase();
}

interface Props {
  alias: string;
  onClose: () => void;
  onSubmit: (payload: { regionBoundaryId?: string; candidateRegionIds?: string[] }) => void;
  isSubmitting?: boolean;
}

export function CreateAliasModal({ alias, onClose, onSubmit, isSubmitting }: Props) {
  const [search, setSearch] = useState('');
  const [ambiguous, setAmbiguous] = useState(false);
  const [selectedRegionId, setSelectedRegionId] = useState<string>('');
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin', 'location-learning', 'regions'],
    queryFn: fetchRegions,
    staleTime: 5 * 60 * 1000,
  });

  const filteredRegions = useMemo(() => {
    const regions = data?.regions ?? [];
    const q = normalizeText(search);
    if (!q) return regions;
    return regions.filter((r) => normalizeText(`${r.name} ${r.borough ?? ''}`).includes(q));
  }, [data?.regions, search]);

  const canSubmit = ambiguous ? selectedCandidateIds.length >= 2 : Boolean(selectedRegionId);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Create Location Alias</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-gray-500 hover:bg-gray-100"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-gray-700">Alias (query text)</label>
          <input
            type="text"
            value={alias}
            disabled
            className="w-full rounded border bg-gray-50 px-3 py-2 font-mono text-sm"
          />
        </div>

        <div className="mb-4 flex items-center gap-2">
          <input
            id="ambiguous-alias"
            type="checkbox"
            checked={ambiguous}
            onChange={(e) => {
              setAmbiguous(e.target.checked);
              setSelectedRegionId('');
              setSelectedCandidateIds([]);
            }}
          />
          <label htmlFor="ambiguous-alias" className="text-sm text-gray-700">
            Ambiguous (multiple regions)
          </label>
        </div>

        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-gray-700">Maps to Region</label>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search regions…"
            className="mb-2 w-full rounded border px-3 py-2 text-sm"
          />

          {isLoading ? (
            <div className="text-sm text-gray-500">Loading regions…</div>
          ) : error ? (
            <div className="text-sm text-red-600">Failed to load regions</div>
          ) : (
            <select
              value={ambiguous ? selectedCandidateIds : selectedRegionId}
              multiple={ambiguous}
              onChange={(e) => {
                if (!ambiguous) {
                  setSelectedRegionId(e.target.value);
                  return;
                }
                const selected = Array.from(e.target.selectedOptions).map((o) => o.value);
                setSelectedCandidateIds(selected);
              }}
              className="w-full rounded border px-3 py-2 text-sm"
              size={8}
            >
              {filteredRegions.map((region) => (
                <option key={region.id} value={region.id}>
                  {region.name}
                  {region.borough ? ` (${region.borough})` : ''}
                </option>
              ))}
            </select>
          )}

          {ambiguous ? (
            <div className="mt-2 text-xs text-gray-500">
              Select at least 2 regions for an ambiguous alias.
            </div>
          ) : null}
        </div>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded border px-4 py-2 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSubmit || isSubmitting}
            onClick={() => {
              onSubmit(
                ambiguous
                  ? { candidateRegionIds: selectedCandidateIds }
                  : { regionBoundaryId: selectedRegionId }
              );
            }}
            className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {isSubmitting ? 'Creating…' : 'Create Alias'}
          </button>
        </div>
      </div>
    </div>
  );
}
