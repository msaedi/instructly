// frontend/components/WeekCalendarGrid.tsx
import React from 'react';

interface TimeSlot {
  start_time: string;
  end_time: string;
  is_available: boolean;
}

interface DateInfo {
  date: Date;
  dateStr: string;
  dayOfWeek: string;
  fullDate: string;
}

interface WeekCalendarGridProps {
  weekDates: DateInfo[];
  startHour?: number;
  endHour?: number;
  renderCell: (date: string, hour: number) => React.ReactNode;
  renderMobileCell?: (date: string, hour: number) => React.ReactNode; // Add this
  onNavigateWeek?: (direction: 'prev' | 'next') => void;
  currentWeekDisplay?: string;
}

const WeekCalendarGrid: React.FC<WeekCalendarGridProps> = ({
  weekDates,
  startHour = 8,
  endHour = 20,
  renderCell,
  renderMobileCell, // Add this
  onNavigateWeek,
  currentWeekDisplay
}) => {
  // Generate hours array based on start and end
  const hours = Array.from(
    { length: endHour - startHour + 1 }, 
    (_, i) => startHour + i
  );

  const formatHour = (hour: number) => {
    const period = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:00 ${period}`;
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <div className="mb-4">
        <h3 className="text-lg font-semibold">Week Schedule</h3>
        <p className="text-sm text-gray-600">Click time slots to toggle availability</p>
      </div>

      {/* Desktop Grid */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full table-fixed">
          <thead>
            <tr>
              <th className="text-left p-2 text-gray-600 w-24">Time</th>
              {weekDates.map((dateInfo, index) => (
                <th key={index} className="text-center p-2 text-gray-600 w-32">
                  <div className="font-semibold capitalize">{dateInfo.dayOfWeek}</div>
                  <div className="text-sm font-normal">{dateInfo.dateStr}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {hours.map(hour => (
              <tr key={hour} className="border-t">
                <td className="p-2 text-sm text-gray-600 w-24">
                  {formatHour(hour)}
                </td>
                {weekDates.map((dateInfo) => (
                  <td key={`${dateInfo.fullDate}-${hour}`} className="p-1 w-32">
                    {renderCell(dateInfo.fullDate, hour)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile List View */}
      <div className="md:hidden space-y-4">
        {weekDates.map((dateInfo, index) => {
          const isPastDate = new Date(dateInfo.fullDate) < new Date(new Date().toDateString());
          
          return (
            <div key={index} className={`border rounded-lg p-4 ${isPastDate ? 'bg-gray-50' : ''}`}>
              <h3 className="font-semibold capitalize mb-1">{dateInfo.dayOfWeek}</h3>
              <p className="text-sm text-gray-600 mb-3">
                {dateInfo.dateStr}
                {isPastDate && <span className="text-gray-500 ml-2">(Past date)</span>}
              </p>
              <div className="grid grid-cols-3 gap-2">
                {hours.map(hour => (
                  <React.Fragment key={`${dateInfo.fullDate}-${hour}`}>
                    {renderMobileCell ? renderMobileCell(dateInfo.fullDate, hour) : renderCell(dateInfo.fullDate, hour)}
                  </React.Fragment>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default WeekCalendarGrid;