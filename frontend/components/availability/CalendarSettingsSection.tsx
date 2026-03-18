import { ToggleSwitch } from '@/components/ui/ToggleSwitch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  CALENDAR_BUFFER_OPTIONS,
  TRAVEL_BUFFER_OPTIONS,
  type CalendarSettingsDraft,
} from './calendarSettings';

type CalendarSettingsSaveState = 'idle' | 'saving' | 'saved';

interface CalendarSettingsSectionProps {
  value: CalendarSettingsDraft;
  saveState: CalendarSettingsSaveState;
  disabled?: boolean;
  onNonTravelChange: (minutes: number) => void;
  onTravelChange: (minutes: number) => void;
  onOvernightProtectionChange: (enabled: boolean) => void;
  onOpenCalendarProtectionsInfo?: () => void;
}

function formatMinutesLabel(minutes: number): string {
  return `${minutes} min`;
}

const settingsCardClassName =
  'rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/50';

export default function CalendarSettingsSection({
  value,
  saveState,
  disabled = false,
  onNonTravelChange,
  onTravelChange,
  onOvernightProtectionChange,
}: CalendarSettingsSectionProps) {
  const saveLabel =
    saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? 'Saved' : null;

  return (
    <section
      aria-labelledby="calendar-settings-heading"
      className="mt-8 border-t border-gray-200 pt-6 dark:border-gray-700"
    >
      <div className="flex items-start justify-between gap-4">
        <h2
          id="calendar-settings-heading"
          className="text-lg font-semibold text-gray-900 dark:text-gray-100"
        >
          Buffer between lessons
        </h2>
        {saveLabel ? (
          <p
            className="shrink-0 text-sm font-medium text-gray-500 dark:text-gray-400"
            data-testid="calendar-settings-save-state"
          >
            {saveLabel}
          </p>
        ) : null}
      </div>

      {/* Two side-by-side buffer cards */}
      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className={settingsCardClassName}>
          <div className="flex items-center justify-between gap-3 mb-3">
            <label
              htmlFor="calendar-non-travel-buffer"
              className="text-sm font-semibold text-gray-900 dark:text-gray-100"
            >
              Staying put
            </label>
            <Select
              value={String(value.nonTravelBufferMinutes)}
              onValueChange={(next) => onNonTravelChange(Number.parseInt(next, 10))}
              disabled={disabled}
            >
              <SelectTrigger
                id="calendar-non-travel-buffer"
                aria-label="Staying put buffer"
                className="w-28"
              >
                <SelectValue placeholder="Select" />
              </SelectTrigger>
              <SelectContent>
                {CALENDAR_BUFFER_OPTIONS.map((minutes) => (
                  <SelectItem key={minutes} value={String(minutes)}>
                    {formatMinutesLabel(minutes)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
            Time between lessons where you&apos;re not traveling — back-to-back online sessions,
            students coming to your studio, or switching between online and studio. Enough time
            for one student to leave, a quick break, and the next to arrive or log in. Most
            instructors find 10–15 minutes works well.
          </p>
        </div>

        <div className={settingsCardClassName}>
          <div className="flex items-center justify-between gap-3 mb-3">
            <label
              htmlFor="calendar-travel-buffer"
              className="text-sm font-semibold text-gray-900 dark:text-gray-100"
            >
              Traveling to student
            </label>
            <Select
              value={String(value.travelBufferMinutes)}
              onValueChange={(next) => onTravelChange(Number.parseInt(next, 10))}
              disabled={disabled}
            >
              <SelectTrigger
                id="calendar-travel-buffer"
                aria-label="Traveling to student buffer"
                className="w-28"
              >
                <SelectValue placeholder="Select" />
              </SelectTrigger>
              <SelectContent>
                {TRAVEL_BUFFER_OPTIONS.map((minutes) => (
                  <SelectItem key={minutes} value={String(minutes)}>
                    {formatMinutesLabel(minutes)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
            Time between lessons when you&apos;re going to or coming from a student&apos;s location.
            Include everything: wrapping up and packing your materials, leaving the building,
            getting to your next location (subway delays, Uber wait times, walking from the
            station), finding the address, buzzing in, and setting up. Aim to arrive 5–10 minutes
            early. In NYC, most instructors need 45–75 minutes.
          </p>
        </div>
      </div>

      {/* Overnight booking protection — full-width card, toggle flush right */}
      <div
        className={`mt-4 flex items-start justify-between gap-4 ${settingsCardClassName}`}
      >
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Overnight booking protection
          </h3>
          <p className="mt-1 text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
            Prevents students from booking early morning slots overnight after 8pm.
          </p>
          <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
            Online/studio slots before 9am and travel slots before 11am are protected from
            bookings made after 8pm.
          </p>
        </div>
        <div className="shrink-0">
          <ToggleSwitch
            checked={value.overnightProtectionEnabled}
            onChange={() => onOvernightProtectionChange(!value.overnightProtectionEnabled)}
            disabled={disabled}
            ariaLabel="Overnight booking protection"
          />
        </div>
      </div>
    </section>
  );
}
