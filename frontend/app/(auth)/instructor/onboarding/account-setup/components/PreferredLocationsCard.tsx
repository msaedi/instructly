'use client';

import { ChevronDown } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import { PlacesAutocompleteInput } from '@/components/forms/PlacesAutocompleteInput';

type PreferredLocationsCardProps = {
  context?: 'dashboard' | 'onboarding';
  isOpen?: boolean;
  onToggle?: () => void;
  preferredAddress: string;
  setPreferredAddress: (value: string) => void;
  preferredLocations: string[];
  setPreferredLocations: Dispatch<SetStateAction<string[]>>;
  preferredLocationTitles: Record<string, string>;
  setPreferredLocationTitles: Dispatch<SetStateAction<Record<string, string>>>;
  neutralLocations: string;
  setNeutralLocations: (value: string) => void;
  neutralPlaces: string[];
  setNeutralPlaces: Dispatch<SetStateAction<string[]>>;
};

export function PreferredLocationsCard({
  context = 'dashboard',
  isOpen = true,
  onToggle,
  preferredAddress,
  setPreferredAddress,
  preferredLocations,
  setPreferredLocations,
  preferredLocationTitles,
  setPreferredLocationTitles,
  neutralLocations,
  setNeutralLocations,
  neutralPlaces,
  setNeutralPlaces,
}: PreferredLocationsCardProps) {
  const collapsible = context !== 'onboarding' && typeof onToggle === 'function';
  const expanded = collapsible ? Boolean(isOpen) : true;

  const header = (
    <div className="flex items-center gap-3">
      <div className="flex flex-col text-left">
        <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Class Locations</span>
        <span className="text-sm text-gray-500">List studio or shared spaces where you regularly teach.</span>
      </div>
    </div>
  );

  const maxTeachingLocations = 2;
  const maxPublicSpaces = 2;

  const addPreferredLocation = () => {
    const value = preferredAddress.trim();
    if (!value || preferredLocations.length >= maxTeachingLocations) return;
    setPreferredLocations((prev) => (prev.includes(value) ? prev : [...prev, value]));
    setPreferredAddress('');
  };

  const removePreferredLocation = (loc: string) => {
    setPreferredLocations((prev) => prev.filter((x) => x !== loc));
  };

  const addNeutralPlace = () => {
    const value = neutralLocations.trim();
    if (!value || neutralPlaces.length >= maxPublicSpaces) return;
    setNeutralPlaces((prev) => (prev.includes(value) ? prev : [...prev, value]));
    setNeutralLocations('');
  };

  const removeNeutralPlace = (place: string) => {
    setNeutralPlaces((prev) => prev.filter((x) => x !== place));
  };

  return (
    <section className="bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
      {collapsible ? (
        <button type="button" className="w-full flex items-center justify-between mb-4 text-left" onClick={onToggle} aria-expanded={expanded}>
          {header}
          <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </button>
      ) : (
        <div className="mb-4">{header}</div>
      )}

      {expanded && (
        <div className="space-y-6" data-testid="preferred-places-card">
          <div>
            <p className="text-gray-600 mt-1 mb-2">Preferred Teaching Location</p>
            <p className="text-xs text-gray-600 mb-2">Add a studio, gym, or home address if you teach from a fixed location.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start mt-3 sm:mt-0">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <PlacesAutocompleteInput
                    data-testid="ptl-input"
                    value={preferredAddress}
                    onValueChange={setPreferredAddress}
                    placeholder="Type address..."
                    inputClassName="h-10 border border-gray-300 pl-3 pr-12 text-sm leading-10 focus:border-purple-500"
                  />
                  <button
                    type="button"
                    data-testid="ptl-add"
                    onClick={addPreferredLocation}
                    aria-label="Add address"
                    disabled={preferredLocations.length >= maxTeachingLocations}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                  >
                    <span className="text-base leading-none">+</span>
                  </button>
                </div>
              </div>
              <div className="min-h-10 flex flex-wrap items-start gap-4 w-full mt-4 sm:mt-0">
                {preferredLocations.map((loc, index) => (
                  <div key={loc} className="relative w-full sm:w-1/2 min-w-0 pt-4 sm:pt-0">
                    <input
                      type="text"
                      placeholder="..."
                      data-testid={`ptl-chip-label-${index}`}
                      value={preferredLocationTitles[loc] || ''}
                      onChange={(e) =>
                        setPreferredLocationTitles((prev) => ({
                          ...prev,
                          [loc]: e.target.value,
                        }))
                      }
                      className="absolute -top-2 sm:-top-5 left-1 text-xs text-[#7E22CE] bg-gray-100 px-1 py-0.5 rounded border-transparent ring-0 shadow-none outline-none focus:outline-none focus-visible:outline-none focus:ring-0 focus-visible:ring-0 focus:border-transparent focus-visible:border-transparent cursor-text"
                      style={{ outline: 'none', outlineOffset: 0, boxShadow: 'none' }}
                    />
                    <span
                      data-testid={`ptl-chip-${index}`}
                      className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 h-10 text-sm w-full min-w-0"
                    >
                      <span className="truncate min-w-0" title={loc}>{loc}</span>
                      <button
                        type="button"
                        aria-label={`Remove ${loc}`}
                        className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                        onClick={() => removePreferredLocation(loc)}
                      >
                        &times;
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div>
            <p className="text-gray-600 mt-1 mb-2">Preferred Public Spaces</p>
            <p className="text-xs text-gray-600 mb-2">Suggest public spaces where you’re comfortable teaching (e.g., library, park, coffee shop).</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <PlacesAutocompleteInput
                    data-testid="pps-input"
                    value={neutralLocations}
                    onValueChange={setNeutralLocations}
                    placeholder="Type location..."
                    inputClassName="h-10 border border-gray-300 pl-3 pr-12 text-sm leading-10 focus:border-purple-500"
                  />
                  <button
                    type="button"
                    data-testid="pps-add"
                    onClick={addNeutralPlace}
                    aria-label="Add public space"
                    disabled={neutralPlaces.length >= maxPublicSpaces}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 focus:outline-none no-hover-shadow disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                  >
                    <span className="text-base leading-none">+</span>
                  </button>
                </div>
              </div>
              <div className="min-h-10 flex flex-col sm:flex-row items-start gap-4 w-full">
                {neutralPlaces.map((place, index) => (
                  <div key={place} className="relative w-full sm:w-1/2 min-w-0">
                    <span
                      data-testid={`pps-chip-${index}`}
                      className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 h-10 text-sm w-full min-w-0"
                    >
                      <span className="truncate min-w-0" title={place}>{place}</span>
                      <button
                        type="button"
                        aria-label={`Remove ${place}`}
                        className="ml-auto text-[#7E22CE] rounded-full w-6 h-6 min-w-6 min-h-6 aspect-square inline-flex items-center justify-center hover:bg-purple-50 no-hover-shadow shrink-0"
                        onClick={() => removeNeutralPlace(place)}
                      >
                        &times;
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
