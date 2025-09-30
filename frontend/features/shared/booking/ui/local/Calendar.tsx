'use client';

interface CalendarProps {
  currentMonth: Date;
  selectedDate: string | null;
  availableDates: string[];
  preSelectedDate?: string;
  onDateSelect: (date: string) => void;
  onMonthChange: (d: Date) => void;
}

export default function Calendar({ currentMonth, selectedDate, availableDates, preSelectedDate, onDateSelect, onMonthChange }: CalendarProps) {
  // Minimal placeholder calendar that preserves props surface used by callers.
  // Keep behavior neutral and presentational-only; consumers control data.
  const monthName = currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  const days: string[] = Array.from({ length: 14 }).map((_, i) => {
    const d = new Date(currentMonth);
    d.setDate(d.getDate() + i);
    return d.toISOString().split('T')[0] || '';
  });
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <button onClick={() => { const d = new Date(currentMonth); d.setMonth(d.getMonth() - 1); onMonthChange(d); }} className="px-2 py-1 border rounded">Prev</button>
        <div className="text-sm font-medium">{monthName}</div>
        <button onClick={() => { const d = new Date(currentMonth); d.setMonth(d.getMonth() + 1); onMonthChange(d); }} className="px-2 py-1 border rounded">Next</button>
      </div>
      <div className="grid grid-cols-7 gap-2">
        {days.map((iso) => {
          const selectable = availableDates.includes(iso as string);
          const isSel = selectedDate === iso || preSelectedDate === iso;
          const label = iso;
          return (
            <button
              key={iso}
              type="button"
              data-testid={`cal-day-${label}`}
              aria-label={label}
              disabled={!selectable}
              onClick={() => selectable && onDateSelect(iso)}
              className={`h-10 text-xs border rounded ${selectable ? 'hover:bg-gray-50' : 'opacity-40 cursor-not-allowed'} ${isSel ? 'bg-blue-600 text-white' : ''}`}
            >
              {label.slice(5)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
