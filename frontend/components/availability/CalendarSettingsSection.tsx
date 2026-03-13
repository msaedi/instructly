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
}

function formatMinutesLabel(minutes: number): string {
  return `${minutes} minutes`;
}

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
        <div>
          <h2
            id="calendar-settings-heading"
            className="text-lg font-semibold text-gray-900 dark:text-gray-100"
          >
            Buffer between lessons
          </h2>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            These settings save separately from your teaching grid and apply automatically to student
            bookings.
          </p>
        </div>
        {saveLabel ? (
          <p
            className="shrink-0 text-sm font-medium text-gray-500 dark:text-gray-400"
            data-testid="calendar-settings-save-state"
          >
            {saveLabel}
          </p>
        ) : null}
      </div>

      <div className="mt-5 space-y-4">
        <div className="grid gap-3 rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/50 md:grid-cols-[minmax(0,1fr)_220px] md:items-center">
          <div>
            <label
              htmlFor="calendar-non-travel-buffer"
              className="text-sm font-medium text-gray-900 dark:text-gray-100"
            >
              When staying put (online/studio)
            </label>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Adds buffer between online and at-your-location lessons.
            </p>
          </div>
          <Select
            value={String(value.nonTravelBufferMinutes)}
            onValueChange={(next) => onNonTravelChange(Number.parseInt(next, 10))}
            disabled={disabled}
          >
            <SelectTrigger
              id="calendar-non-travel-buffer"
              aria-label="When staying put buffer"
              className="w-full"
            >
              <SelectValue placeholder="Select minutes" />
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

        <div className="grid gap-3 rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900/50 md:grid-cols-[minmax(0,1fr)_220px] md:items-center">
          <div>
            <label
              htmlFor="calendar-travel-buffer"
              className="text-sm font-medium text-gray-900 dark:text-gray-100"
            >
              When traveling to student
            </label>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Adds travel time after student-location lessons before the next lesson can start.
            </p>
          </div>
          <Select
            value={String(value.travelBufferMinutes)}
            onValueChange={(next) => onTravelChange(Number.parseInt(next, 10))}
            disabled={disabled}
          >
            <SelectTrigger
              id="calendar-travel-buffer"
              aria-label="When traveling to student buffer"
              className="w-full"
            >
              <SelectValue placeholder="Select minutes" />
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
      </div>

      <div className="mt-6 rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-start justify-between gap-4">
          <div className="pr-4">
            <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              Overnight Booking Protection
            </h3>
            <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-400">
              When enabled, students can&apos;t book early morning lessons overnight. Online/studio
              slots before 9am and travel slots before 11am are protected from bookings made after
              8pm.
            </p>
          </div>
          <ToggleSwitch
            checked={value.overnightProtectionEnabled}
            onChange={() => onOvernightProtectionChange(!value.overnightProtectionEnabled)}
            disabled={disabled}
            ariaLabel="Overnight Booking Protection"
          />
        </div>
      </div>
    </section>
  );
}
