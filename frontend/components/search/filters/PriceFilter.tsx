'use client';

import { useState } from 'react';

import { FilterButton } from './FilterButton';

const PRICE_MIN = 30;
const PRICE_MAX = 300;
const MIN_GAP = 10;

interface PriceFilterProps {
  isOpen: boolean;
  onToggle: () => void;
  min: number | null;
  max: number | null;
  onChange: (min: number | null, max: number | null) => void;
  onClose: () => void;
}

export function PriceFilter({
  isOpen,
  onToggle,
  min,
  max,
  onChange,
  onClose,
}: PriceFilterProps) {
  const [draftMin, setDraftMin] = useState(min ?? PRICE_MIN);
  const [draftMax, setDraftMax] = useState(max ?? PRICE_MAX);

  const handleToggle = () => {
    if (!isOpen) {
      setDraftMin(min ?? PRICE_MIN);
      setDraftMax(max ?? PRICE_MAX);
    }
    onToggle();
  };

  const handleApply = () => {
    onChange(draftMin > PRICE_MIN ? draftMin : null, draftMax < PRICE_MAX ? draftMax : null);
    onClose();
  };

  const handleClear = () => {
    setDraftMin(PRICE_MIN);
    setDraftMax(PRICE_MAX);
    onChange(null, null);
    onClose();
  };

  const isActive = min !== null || max !== null;
  const label = isActive ? `$${min ?? PRICE_MIN} - $${max ?? PRICE_MAX}` : 'Price';

  return (
    <FilterButton
      label={label}
      isOpen={isOpen}
      isActive={isActive}
      onClick={handleToggle}
      onClickOutside={onClose}
    >
      <div className="p-4 w-[280px]">
        <h3 className="font-medium text-gray-900 mb-4">Price Range</h3>

        <div className="relative pt-1 pb-4">
          <div className="h-2 bg-gray-200 rounded-full" />
          <div
            className="absolute h-2 bg-purple-500 rounded-full top-1"
            style={{
              left: `${((draftMin - PRICE_MIN) / (PRICE_MAX - PRICE_MIN)) * 100}%`,
              right: `${100 - ((draftMax - PRICE_MIN) / (PRICE_MAX - PRICE_MIN)) * 100}%`,
            }}
          />

          <input
            type="range"
            min={PRICE_MIN}
            max={PRICE_MAX}
            value={draftMin}
            onChange={(event) => {
              const next = Math.min(Number(event.target.value), draftMax - MIN_GAP);
              setDraftMin(next);
            }}
            className="absolute w-full h-2 top-1 appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-purple-500 [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-pointer"
          />

          <input
            type="range"
            min={PRICE_MIN}
            max={PRICE_MAX}
            value={draftMax}
            onChange={(event) => {
              const next = Math.max(Number(event.target.value), draftMin + MIN_GAP);
              setDraftMax(next);
            }}
            className="absolute w-full h-2 top-1 appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-purple-500 [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-pointer"
          />
        </div>

        <div className="flex justify-between text-sm text-gray-600 mt-2">
          <span>${draftMin}/hr</span>
          <span>${draftMax}/hr</span>
        </div>

        <div className="flex items-center gap-3 mt-4">
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
            <input
              type="number"
              value={draftMin}
              onChange={(event) => {
                const next = Math.max(PRICE_MIN, Math.min(Number(event.target.value), draftMax - MIN_GAP));
                setDraftMin(next);
              }}
              className="w-full pl-7 pr-2 py-2 border rounded-lg text-sm"
            />
          </div>
          <span className="text-gray-400">-</span>
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
            <input
              type="number"
              value={draftMax}
              onChange={(event) => {
                const next = Math.min(PRICE_MAX, Math.max(Number(event.target.value), draftMin + MIN_GAP));
                setDraftMax(next);
              }}
              className="w-full pl-7 pr-2 py-2 border rounded-lg text-sm"
            />
          </div>
        </div>

        <div className="flex justify-between mt-4 pt-3 border-t border-gray-100">
          <button
            type="button"
            onClick={handleClear}
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="px-4 py-1.5 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700"
          >
            Apply
          </button>
        </div>
      </div>
    </FilterButton>
  );
}
