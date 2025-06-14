import React from 'react';
import { BookedSlotPreview, getLocationTypeIcon } from '@/types/booking';

interface BookedSlotCellProps {
  slot: BookedSlotPreview;
  isFirstSlot: boolean;
  isMobile?: boolean;
  onClick: () => void;
}

const BookedSlotCell: React.FC<BookedSlotCellProps> = ({ 
  slot, 
  isFirstSlot, 
  isMobile = false,
  onClick 
}) => {
  // For mobile, show less detail
  if (isMobile) {
    return (
      <button
        onClick={onClick}
        className="w-full h-full p-1 rounded bg-red-100 border border-red-300 
                   hover:bg-red-200 active:bg-red-300 transition-colors cursor-pointer
                   flex flex-col justify-center items-center text-xs"
        aria-label={`Booking with ${slot.student_first_name} ${slot.student_last_initial} for ${slot.service_name}`}
      >
        {isFirstSlot ? (
          <>
            <span className="text-base">📅</span>
            <span className="font-medium text-[10px]">
              {slot.student_first_name[0]}{slot.student_last_initial[0]}
            </span>
            <span className="text-[9px] text-gray-700">
              {slot.service_name.substring(0, 5)}
            </span>
          </>
        ) : (
          <span className="text-[10px] text-gray-600">...</span>
        )}
      </button>
    );
  }

  // Desktop view - more detailed
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
          {/* Main info - always visible */}
          <div className="font-semibold flex items-center justify-center gap-1 text-red-800">
            <span className="text-sm">📅</span>
            <span>
              {slot.student_first_name} {slot.student_last_initial}
            </span>
          </div>
          
          {/* Service name */}
          <div className="text-gray-700 text-center">
            {slot.service_name}
          </div>
          
          {/* Location info - show icon + area */}
          <div className="text-gray-600 text-center flex items-center justify-center gap-1">
            <span>{getLocationTypeIcon(slot.location_type)}</span>
            <span>{slot.service_area_short}</span>
          </div>
          
          {/* Duration badge for multi-hour bookings */}
          {slot.duration_minutes > 60 && (
            <div className="text-[10px] text-gray-500 text-center">
              {Math.floor(slot.duration_minutes / 60)}h {slot.duration_minutes % 60 > 0 ? `${slot.duration_minutes % 60}m` : ''}
            </div>
          )}
          
          {/* Hover hint */}
          <div className="text-[10px] text-gray-500 text-center opacity-0 group-hover:opacity-100 transition-opacity">
            Click for details →
          </div>
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