import { MonitorCheck } from 'lucide-react';
import { TAG_NONE, TAG_NO_TRAVEL, TAG_ONLINE_ONLY } from '@/lib/calendar/bitset';
import {
  type AvailabilityPaintMode,
  type EditableFormatTag,
} from './calendarSettings';
import NoTravelIcon from './NoTravelIcon';

interface FormatTagPaintToolbarProps {
  availableTagOptions: EditableFormatTag[];
  value: AvailabilityPaintMode;
  onChange: (value: AvailabilityPaintMode) => void;
}

function getToolbarOptionTitle(option: AvailabilityPaintMode): string {
  if (option === TAG_NO_TRAVEL) {
    return 'No Travel';
  }

  if (option === TAG_ONLINE_ONLY) {
    return 'Online';
  }

  return 'All';
}

const pillColors: Record<number, { active: string; inactive: string }> = {
  [TAG_NONE]: {
    active: 'bg-(--color-brand) text-white border-(--color-brand)',
    inactive: 'bg-(--color-brand-lavender) text-(--color-brand) border-(--color-brand-lavender) dark:border-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  },
  [TAG_ONLINE_ONLY]: {
    active: 'bg-(--color-online-green) text-white border-(--color-online-green)',
    inactive: 'bg-(--color-online-green-light) text-(--color-online-green) border-(--color-online-green-light) dark:border-emerald-700/60 dark:bg-[#064E3B]/30 dark:text-emerald-300',
  },
  [TAG_NO_TRAVEL]: {
    active: 'bg-(--color-notravel-yellow) text-(--color-notravel-brown) border-(--color-notravel-yellow)',
    inactive: 'bg-(--color-notravel-yellow-light) text-(--color-notravel-brown) border-(--color-notravel-yellow-light) dark:border-amber-700/60 dark:bg-[#78350F]/30 dark:text-amber-300',
  },
};

export default function FormatTagPaintToolbar({
  availableTagOptions,
  value,
  onChange,
}: FormatTagPaintToolbarProps) {
  const options: AvailabilityPaintMode[] = [TAG_NONE];
  if (availableTagOptions.includes(TAG_ONLINE_ONLY)) {
    options.push(TAG_ONLINE_ONLY);
  }
  if (availableTagOptions.includes(TAG_NO_TRAVEL)) {
    options.push(TAG_NO_TRAVEL);
  }

  return (
    <div
      data-testid="availability-paint-toolbar"
      className="flex flex-col items-start gap-3 sm:flex-row sm:items-center"
    >
      <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
        Availability format:
      </span>
      <div
        role="radiogroup"
        aria-label="Availability format"
        className="flex flex-wrap items-center gap-2"
      >
        {options.map((option) => {
          const active = value === option;
          const colors = pillColors[option] ?? pillColors[TAG_NONE]!;
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={active}
              aria-label={`${getToolbarOptionTitle(option)}${active ? ' (selected)' : ''}`}
              onClick={() => onChange(option)}
              className={`inline-flex w-28 shrink-0 items-center justify-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition-colors focus-visible:outline-none   ${
                active ? colors.active : colors.inactive
              }`}
            >
              {option === TAG_ONLINE_ONLY ? (
                <MonitorCheck className="h-3.5 w-3.5" aria-hidden="true" />
              ) : option === TAG_NO_TRAVEL ? (
                <span className="inline-flex h-3.5 w-3.5 shrink-0">
                  <NoTravelIcon data-testid="paint-mode-no-travel-icon" />
                </span>
              ) : null}
              {getToolbarOptionTitle(option)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
