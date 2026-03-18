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
    active: 'bg-[#7E22CE] text-white border-[#7E22CE]',
    inactive: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-700',
  },
  [TAG_ONLINE_ONLY]: {
    active: 'bg-[#2563EB] text-white border-[#2563EB]',
    inactive: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-700',
  },
  [TAG_NO_TRAVEL]: {
    active: 'bg-[#059669] text-white border-[#059669]',
    inactive: 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-200 dark:border-gray-600 dark:hover:bg-gray-700',
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
      className="flex items-center gap-3"
    >
      <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
        Availability format:
      </span>
      <div
        role="radiogroup"
        aria-label="Availability format"
        className="flex items-center gap-2"
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
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
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
