'use client';

import { ChevronDown, MapPin } from 'lucide-react';
import type { MutableRefObject } from 'react';
import type { ServiceAreaItem } from '@/features/instructor-profile/types';

type ServiceAreasCardProps = {
  context?: 'dashboard' | 'onboarding';
  isOpen?: boolean;
  onToggle?: () => void;
  globalNeighborhoodFilter: string;
  onGlobalFilterChange: (value: string) => void;
  nycBoroughs: readonly string[];
  boroughNeighborhoods: Record<string, ServiceAreaItem[]>;
  selectedNeighborhoods: Set<string>;
  onToggleNeighborhood: (id: string) => void;
  openBoroughs: Set<string>;
  onToggleBoroughAccordion: (borough: string) => Promise<void> | void;
  loadBoroughNeighborhoods: (borough: string) => Promise<ServiceAreaItem[]>;
  toggleBoroughAll: (borough: string, value: boolean, itemsOverride?: ServiceAreaItem[]) => void;
  boroughAccordionRefs: MutableRefObject<Record<string, HTMLDivElement | null>>;
  idToItem: Record<string, ServiceAreaItem>;
  isNYC: boolean;
  formatNeighborhoodName: (value: string) => string;
};

export function ServiceAreasCard({
  context = 'dashboard',
  isOpen = true,
  onToggle,
  globalNeighborhoodFilter,
  onGlobalFilterChange,
  nycBoroughs,
  boroughNeighborhoods,
  selectedNeighborhoods,
  onToggleNeighborhood,
  openBoroughs,
  onToggleBoroughAccordion,
  loadBoroughNeighborhoods,
  toggleBoroughAll,
  boroughAccordionRefs,
  idToItem,
  isNYC,
  formatNeighborhoodName,
}: ServiceAreasCardProps) {
  const collapsible = context !== 'onboarding' && typeof onToggle === 'function';
  const expanded = collapsible ? Boolean(isOpen) : true;

  const header = (
    <div className="flex items-center gap-3">
      <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
        <MapPin className="w-6 h-6 text-[#7E22CE]" />
      </div>
      <div className="flex flex-col text-left">
        <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Service Areas</span>
        <span className="text-sm text-gray-500">Select the neighborhoods where you’re available for lessons.</span>
      </div>
    </div>
  );

  const searchHits = nycBoroughs
    .flatMap((borough) => boroughNeighborhoods[borough] || [])
    .filter((n) => (n['name'] || '').toLowerCase().includes(globalNeighborhoodFilter.toLowerCase()));

  return (
    <section className="bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
      {collapsible ? (
        <button
          type="button"
          className="w-full flex items-center justify-between mb-4 text-left"
          onClick={onToggle}
          aria-expanded={expanded}
          data-testid="service-areas-card"
        >
          {header}
          <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </button>
      ) : (
        <div className="flex items-center justify-between mb-4" data-testid="service-areas-card">
          {header}
        </div>
      )}

      {expanded && (
        <>
          <p className="text-gray-600 mt-1 mb-2">Select the neighborhoods where you teach</p>
          <div className="mb-3">
            <input
              type="text"
              value={globalNeighborhoodFilter}
              onChange={(e) => onGlobalFilterChange(e.target.value)}
              placeholder="Search neighborhoods..."
              className="w-full rounded-md border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
            />
          </div>
          {globalNeighborhoodFilter.trim().length > 0 && (
            <div className="mb-3">
              <div className="text-sm text-gray-700 mb-2">Results</div>
              <div className="flex flex-wrap gap-2">
                {searchHits.map((n) => {
                  const nid = n['neighborhood_id'] || (n as Record<string, unknown>)['id'] as string;
                  if (!nid) return null;
                  const checked = selectedNeighborhoods.has(nid);
                  return (
                    <button
                      key={`global-${nid}`}
                      type="button"
                      onClick={() => onToggleNeighborhood(nid)}
                      aria-pressed={checked}
                      className={`inline-flex items-center justify-between px-3 py-1.5 text-sm rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                        checked ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      <span className="truncate text-left">{n['name'] || nid}</span>
                      <span className="ml-2">{checked ? '✓' : '+'}</span>
                    </button>
                  );
                }).filter(Boolean).slice(0, 200)}
                {searchHits.length === 0 && (
                  <div className="text-sm text-gray-500">No matches found</div>
                )}
              </div>
            </div>
          )}

          {selectedNeighborhoods.size > 0 && (
            <div className="mb-3 flex flex-wrap gap-2">
              {Array.from(selectedNeighborhoods).map((nid) => {
                const name = formatNeighborhoodName(idToItem[nid]?.['name'] || String(nid));
                return (
                  <span key={`sel-${nid}`} className="inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white px-3 h-8 text-xs min-w-0">
                    <span className="truncate max-w-[14rem]" title={name}>{name}</span>
                    <button
                      type="button"
                      aria-label={`Remove ${name}`}
                      className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                      onClick={() => onToggleNeighborhood(nid)}
                    >
                      &times;
                    </button>
                  </span>
                );
              })}
            </div>
          )}

          {isNYC ? (
            <div className="space-y-3">
              <div className="mt-3 space-y-3">
                {nycBoroughs.map((borough) => {
                  const isAccordionOpen = openBoroughs.has(borough);
                  const list = boroughNeighborhoods[borough] || [];
                  return (
                    <div
                      key={`accordion-${borough}`}
                      ref={(el) => { boroughAccordionRefs.current[borough] = el; }}
                      className="rounded-xl bg-white shadow-sm overflow-hidden"
                    >
                      <div
                        className="flex items-center justify-between cursor-pointer w-full pl-4 pr-3 md:pl-5 py-2 hover:bg-gray-50 transition-all"
                        onClick={() => { void onToggleBoroughAccordion(borough); }}
                        aria-expanded={isAccordionOpen}
                        role="button"
                        tabIndex={0}
                        data-testid={`service-area-borough-${borough.toLowerCase().replace(/\s+/g, '-')}`}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            void onToggleBoroughAccordion(borough);
                          }
                        }}
                      >
                        <div className="flex items-center gap-2 text-gray-800 font-medium">
                          <span className="tracking-wide text-xs sm:text-sm whitespace-nowrap">{borough}</span>
                          <ChevronDown className={`h-4 w-4 text-gray-600 transition-transform ${isAccordionOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
                        </div>
                        <div className="flex gap-2 text-[11px] sm:text-sm" onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            className="px-2 sm:px-3 py-1 rounded-md bg-purple-100 text-[#7E22CE] hover:bg-purple-200 whitespace-nowrap"
                            onClick={async (e) => {
                              e.stopPropagation();
                              const listNow = boroughNeighborhoods[borough] || (await loadBoroughNeighborhoods(borough));
                              toggleBoroughAll(borough, true, listNow);
                            }}
                          >
                            Select all
                          </button>
                          <button
                            type="button"
                            className="px-2 sm:px-3 py-1 rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 whitespace-nowrap"
                            onClick={async (e) => {
                              e.stopPropagation();
                              const listNow = boroughNeighborhoods[borough] || (await loadBoroughNeighborhoods(borough));
                              toggleBoroughAll(borough, false, listNow);
                            }}
                          >
                            Clear all
                          </button>
                        </div>
                      </div>
                      {isAccordionOpen && (
                        <div className="px-3 pb-3 mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 max-h-80 overflow-y-auto overflow-x-hidden scrollbar-hide">
                          {(list || []).map((n) => {
                            const nid = n['neighborhood_id'] || (n as Record<string, unknown>)['id'] as string;
                            if (!nid) return null;
                            const checked = selectedNeighborhoods.has(nid);
                            const label = formatNeighborhoodName(n['name'] || String(nid));
                            const regionCode = String(n.code || n.ntacode || idToItem[nid]?.ntacode || nid);
                            return (
                              <button
                                key={`${borough}-${nid}`}
                                type="button"
                                onClick={() => onToggleNeighborhood(nid)}
                                aria-pressed={checked}
                                data-testid={`service-area-chip-${regionCode}`}
                                data-state={checked ? 'selected' : 'idle'}
                                className={`inline-flex items-center justify-between w-full min-w-0 px-2 py-1 text-xs rounded-full font-semibold focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 transition-colors no-hover-shadow appearance-none overflow-hidden ${
                                  checked ? 'bg-[#7E22CE] text-white border border-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                }`}
                              >
                                <span className="truncate text-left">{label}</span>
                                <span className="ml-2">{checked ? '✓' : '+'}</span>
                              </button>
                            );
                          })}
                          {list.length === 0 && (
                            <div className="col-span-full text-sm text-gray-500">Loading…</div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="mt-2 rounded-lg border border-dashed border-gray-300 p-4 text-sm text-gray-600">
              Your city is not yet supported for granular neighborhoods. We’ll add it soon.
            </div>
          )}
        </>
      )}
    </section>
  );
}
