// frontend/components/BookedSlotCell.tsx
import React from 'react';
import { BookedSlotPreview, getLocationTypeIcon } from '@/types/booking';

/**
 * BookedSlotCell Component
 * 
 * Displays a booked time slot in the availability calendar grid.
 * Shows different information based on whether it's the first hour of a multi-hour booking.
 * 
 * Features:
 * - Privacy-preserved student names (First + Last Initial)
 * - Location type icons
 * - Service area abbreviations
 * - Duration indicators for multi-hour bookings
 * - Responsive design (mobile vs desktop)
 * - Accessibility support with ARIA labels
 * 
 * @component
 */
interface BookedSlotCellProps {
  /** The booking slot data to display */
  slot: BookedSlotPreview;
  /** Whether this is the first hour of a multi-hour booking */
  isFirstSlot: boolean;
  /** Whether to render in mobile mode (simplified view) */
  isMobile?: boolean;
  /** Click handler for viewing booking details */
  onClick: (e: React.MouseEvent) => void;
}

const BookedSlotCell: React.FC<BookedSlotCellProps> = ({ 
  slot, 
  isFirstSlot, 
  isMobile = false,
  onClick 
}) => {
  /**
   * Format duration for display
   * @param minutes - Total duration in minutes
   * @returns Formatted duration string (e.g., "2h 30m")
   */
  const formatDuration = (minutes: number): string => {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    if (mins === 0) return `${hours}h`;
    return `${hours}h ${mins}m`;
  };

  // Mobile view - simplified display
  if (isMobile) {
    return (
      <button
        onClick={onClick}
        className="w-full h-full p-1 rounded bg-red-100 border border-red-300 
                   hover:bg-red-200 active:bg-red-300 transition-colors cursor-pointer
                   flex flex-col justify-center items-center text-xs"
        aria-label={`Booking with ${slot.student_first_name} ${slot.student_last_initial}`}
      >
        {isFirstSlot ? (
          <>
            <span className="font-semibold text-[11px] text-red-800">
              {slot.student_first_name} {slot.student_last_initial}
            </span>
            <span className="text-[10px] text-gray-600 flex items-center gap-0.5">
              {getLocationTypeIcon(slot.location_type)}
              <span>{slot.service_area_short}</span>
            </span>
          </>
        ) : (
          <span className="text-[10px] text-gray-600">...</span>
        )}
      </button>
    );
  }

  // Desktop view - more detailed information
  return (
    <button
      onClick={onClick}
      className="w-full h-full p-2 rounded bg-red-100 border border-red-300 
                 hover:bg-red-200 active:bg-red-300 transition-all cursor-pointer
                 flex flex-col justify-center items-center text-xs
                 hover:shadow-md group"
      aria-label={`Booking with ${slot.student_first_name} ${slot.student_last_initial} for ${slot.service_name}`}
    >
      {isFirstSlot ? (
        <div className="w-full space-y-1">
          {/* Student name with privacy preservation */}
          <div className="font-semibold text-red-800">
            {slot.student_first_name} {slot.student_last_initial}
          </div>
          
          {/* Location info with icon and area */}
          <div className="text-gray-600 text-center flex items-center justify-center gap-1">
            <span>{getLocationTypeIcon(slot.location_type)}</span>
            <span>{slot.service_area_short}</span>
          </div>
          
          {/* Duration badge for multi-hour bookings */}
          {slot.duration_minutes > 60 && (
            <div className="text-[10px] text-gray-500 text-center">
              {formatDuration(slot.duration_minutes)}
            </div>
          )}
        </div>
      ) : (
        <div className="text-gray-600 text-xs">
          <div>(continuing)</div>
          <div className="text-[10px] text-gray-500 mt-1">
            {slot.student_first_name} {slot.student_last_initial}
          </div>
        </div>
      )}
    </button>
  );
};

export default BookedSlotCell;