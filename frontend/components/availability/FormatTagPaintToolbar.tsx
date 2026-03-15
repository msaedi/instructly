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

function BrushDot({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex h-4 w-4 items-center justify-center rounded-full border transition-colors ${
        active
          ? 'border-[#7E22CE] bg-[#7E22CE]'
          : 'border-gray-400 bg-transparent dark:border-gray-500'
      }`}
      aria-hidden="true"
    >
      {active ? <span className="h-1.5 w-1.5 rounded-full bg-white" /> : null}
    </span>
  );
}

function getToolbarOptionDescription(option: AvailabilityPaintMode): string {
  if (option === TAG_NO_TRAVEL) {
    return 'Online and studio only';
  }

  if (option === TAG_ONLINE_ONLY) {
    return 'Online lessons only';
  }

  return 'All lesson formats';
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

export default function FormatTagPaintToolbar({
  availableTagOptions,
  value,
  onChange,
}: FormatTagPaintToolbarProps) {
  const options: AvailabilityPaintMode[] = [TAG_NONE];
  if (availableTagOptions.includes(TAG_NO_TRAVEL)) {
    options.push(TAG_NO_TRAVEL);
  }
  if (availableTagOptions.includes(TAG_ONLINE_ONLY)) {
    options.push(TAG_ONLINE_ONLY);
  }

  return (
    <div
      data-testid="availability-paint-toolbar"
      className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-gray-50/70 px-4 py-3 dark:border-gray-700 dark:bg-gray-900/50"
    >
      <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Availability</div>
      <div
        role="radiogroup"
        aria-label="Availability"
        className="flex flex-wrap items-start justify-between gap-3"
      >
        {options.map((option) => {
          const active = value === option;
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(option)}
              className={`inline-flex w-[17rem] max-w-full flex-none items-center justify-center gap-3 rounded-full border px-4 py-2 text-center text-sm transition-colors ${
                active
                  ? 'border-[#D4B5F0] bg-[#F3E8FF] text-[#7E22CE] dark:border-purple-400/40 dark:bg-purple-500/20 dark:text-purple-200'
                  : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900/60 dark:text-gray-200 dark:hover:bg-gray-800'
              }`}
            >
              <BrushDot active={active} />
              <span className="font-medium">{getToolbarOptionTitle(option)}</span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {getToolbarOptionDescription(option)}
              </span>
              {option === TAG_ONLINE_ONLY ? (
                <MonitorCheck className="h-4 w-4" aria-hidden="true" />
              ) : option === TAG_NO_TRAVEL ? (
                <NoTravelIcon className="h-4 w-4" data-testid="paint-mode-no-travel-icon" />
              ) : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
