'use client';

interface SummarySectionProps {
  selectedDate: string | null;
  selectedTime: string | null;
  selectedDuration: number;
  price: number;
  onContinue: () => void;
  isComplete: boolean;
}

export default function SummarySection({
  selectedDate,
  selectedTime,
  selectedDuration,
  price,
  onContinue,
  isComplete,
}: SummarySectionProps) {
  // Format date to human-readable format
  const formatDate = (dateStr: string, timeStr: string) => {
    const date = new Date(dateStr);
    const monthNames = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    const month = monthNames[date.getMonth()];
    const day = date.getDate();

    // Convert time to 12-hour format if needed
    const formattedTime =
      timeStr.includes('am') || timeStr.includes('pm') ? timeStr : formatTime24to12(timeStr);

    return `${month} ${day}, ${formattedTime}`;
  };

  // Convert 24-hour time to 12-hour format
  const formatTime24to12 = (time24: string) => {
    const [hours, minutes] = time24.split(':').map(Number);
    const period = hours >= 12 ? 'pm' : 'am';
    const hour12 = hours % 12 || 12;
    return `${hour12}:${minutes.toString().padStart(2, '0')}${period}`;
  };

  // Don't show anything if no selections made
  if (!selectedDate && !selectedTime) {
    return null;
  }

  return (
    <div className="w-full lg:w-[200px]">
      <div className="text-center">
        {/* Request for header */}
        <p className="text-sm mb-3" style={{ color: '#666666' }}>
          Request for:
        </p>

        {/* Date and Time */}
        {selectedDate && selectedTime && (
          <p className="text-lg font-medium mb-3" style={{ color: '#333333', fontSize: '18px' }}>
            {formatDate(selectedDate, selectedTime)}
          </p>
        )}

        {/* Duration and Price */}
        {selectedDuration && price > 0 && (
          <p className="text-base mb-6" style={{ color: '#333333', fontSize: '16px' }}>
            {selectedDuration} min · ${price}
          </p>
        )}

        {/* Continue Button */}
        <button
          onClick={onContinue}
          disabled={!isComplete}
          className={`
            w-full py-3 px-4 rounded font-medium transition-colors
            ${
              isComplete
                ? 'text-white hover:opacity-90'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }
          `}
          style={{
            backgroundColor: isComplete ? '#6B46C1' : undefined,
            height: '44px',
            fontSize: '16px',
            borderRadius: '4px',
          }}
        >
          Select and continue
        </button>

        {/* Helper Text */}
        <p
          className="mt-4 text-sm leading-relaxed"
          style={{
            color: '#666666',
            fontSize: '14px',
            lineHeight: '1.5',
          }}
        >
          Next, confirm your details and start learning
        </p>
      </div>
    </div>
  );
}
