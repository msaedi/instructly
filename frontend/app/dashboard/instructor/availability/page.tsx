// frontend/app/dashboard/instructor/availability/page.tsx
// LEGACY-ONLY: This file is part of the pre-Phoenix dashboard. Do not import from new Phoenix routes.
// Kept for backward compatibility and historical reference. New work should live under (auth)/instructor/*.
'use client';

/**
 * AvailabilityPage Component
 *
 * Manages instructor availability on a week-by-week basis.
 * This is the main page that orchestrates all availability management features
 * using extracted hooks, utilities, and components.
 *
 * Features:
 * - Week-based navigation and editing
 * - Visual calendar grid with time slots
 * - Booking protection (can't modify booked slots)
 * - Preset schedules for quick setup
 * - Copy from previous week functionality
 * - Apply to future weeks with automatic saving
 * - Real-time validation before saving
 * - Mobile-responsive design
 *
 * @component
 * @module pages/instructor/availability (legacy location)
 */

import React, { useState, useCallback, useEffect } from 'react';
import { ArrowLeft, AlertCircle } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

// Custom hooks
import { useWeekSchedule } from '@/hooks/availability/useWeekSchedule';
import { useBookedSlots } from '@/hooks/availability/useBookedSlots';
import { useAvailabilityOperations } from '@/legacy-patterns/useAvailabilityOperations';

// Components
import WeekNavigator from '@/components/availability/WeekNavigator';
import ActionButtons from '@/components/availability/ActionButtons';
import PresetButtons from '@/components/availability/PresetButtons';
import InstructionsCard from '@/components/availability/InstructionsCard';
import WeekCalendarGrid from '@/components/WeekCalendarGrid';
import BookedSlotCell from '@/components/BookedSlotCell';
import TimeSlotButton from '@/components/TimeSlotButton';
import BookingQuickPreview from '@/components/BookingQuickPreview';

// Modals
import ClearWeekConfirmModal from '@/components/modals/ClearWeekConfirmModal';
import ApplyToFutureWeeksModal from '@/components/modals/ApplyToFutureWeeksModal';
import ValidationPreviewModal from '@/components/modals/ValidationPreviewModal';

// Utilities, constants, and types
import { PRESET_SCHEDULES, SUCCESS_MESSAGES, ERROR_MESSAGES } from '@/lib/availability/constants';
import type { TimeSlot, WeekSchedule } from '@/types/availability';
import { isTimeSlotInPast } from '@/lib/availability/dateHelpers';
import { mergeAdjacentSlots, createHourSlot } from '@/legacy-patterns/slotHelpers';
import { logger } from '@/lib/logger';

/**
 * Main availability management page
 *
 * @returns Availability page component
 */
export default function AvailabilityPage(): React.ReactElement {
  const router = useRouter();

  // Core hooks for state management
  const {
    currentWeekStart,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    isLoading,
    existingSlots,
    weekDates,
    message,
    navigateWeek,
    setWeekSchedule,
    setMessage,
    refreshSchedule,
    currentWeekDisplay,
  } = useWeekSchedule();

  const {
    bookedSlots,
    isSlotBooked,
    getBookingForSlot,
    selectedBookingId,
    showBookingPreview,
    fetchBookedSlots,
    handleBookingClick,
    closeBookingPreview,
    refreshBookings,
  } = useBookedSlots();

  const {
    isSaving,
    isValidating,
    validationResults,
    showValidationPreview,
    saveWeekSchedule,
    copyFromPreviousWeek,
    applyToFutureWeeks,
    setShowValidationPreview,
  } = useAvailabilityOperations({
    weekSchedule,
    savedWeekSchedule,
    currentWeekStart,
    existingSlots,
    bookedSlots,
    weekDates,
    onSaveSuccess: async () => {
      await refreshSchedule();
      await refreshBookings(currentWeekStart);
    },
    onScheduleUpdate: (newSchedule) => {
      setWeekSchedule(newSchedule);
    },
  });

  // Local UI state
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // Fetch booked slots when week changes
  useEffect(() => {
    if (!isLoading) {
      fetchBookedSlots(currentWeekStart);
    }
  }, [currentWeekStart, isLoading, fetchBookedSlots]);

  /**
   * Toggle time slot availability
   * This is the main interaction handler for the calendar grid
   */
  const toggleTimeSlot = useCallback(
    (date: string, hour: number) => {
      // Check if time slot is in the past
      if (isTimeSlotInPast(date, hour)) {
        setMessage({
          type: 'error',
          text: ERROR_MESSAGES.PAST_SLOT,
        });
        return;
      }

      // Check if slot is booked
      if (isSlotBooked(date, hour)) {
        setMessage({
          type: 'error',
          text: ERROR_MESSAGES.BOOKED_SLOT,
        });
        return;
      }

      const daySlots = weekSchedule[date] || [];
      const isCurrentlyAvailable = daySlots.some((slot) => {
        const startHour = parseInt(slot.start_time.split(':')[0]);
        const endHour = parseInt(slot.end_time.split(':')[0]);
        return hour >= startHour && hour < endHour;
      });

      logger.info('Toggling time slot', {
        date,
        hour,
        currentlyAvailable: isCurrentlyAvailable,
      });

      let newSlots = daySlots;

      if (isCurrentlyAvailable) {
        // Remove this hour from availability
        newSlots = removeHourFromSlots(daySlots, hour);
      } else {
        // Add this hour to availability
        const newSlot = createHourSlot(hour);
        newSlots = [...daySlots, newSlot].sort((a, b) => a.start_time.localeCompare(b.start_time));

        // Merge adjacent slots while respecting booking boundaries
        newSlots = mergeAdjacentSlots(newSlots, date, bookedSlots);
      }

      setWeekSchedule({
        ...weekSchedule,
        [date]: newSlots,
      });
    },
    [weekSchedule, setWeekSchedule, isSlotBooked, bookedSlots, setMessage]
  );

  /**
   * Remove an hour from availability slots
   */
  const removeHourFromSlots = (slots: TimeSlot[], hour: number): TimeSlot[] => {
    const newSlots: TimeSlot[] = [];

    slots.forEach((slot) => {
      const startHour = parseInt(slot.start_time.split(':')[0]);
      const endHour = parseInt(slot.end_time.split(':')[0]);

      if (hour < startHour || hour >= endHour) {
        // Hour is outside this slot
        newSlots.push(slot);
      } else if (hour === startHour && hour === endHour - 1) {
        // Single hour slot - remove entirely
      } else if (hour === startHour) {
        // Remove from start
        newSlots.push({
          ...slot,
          start_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`,
        });
      } else if (hour === endHour - 1) {
        // Remove from end
        newSlots.push({
          ...slot,
          end_time: `${hour.toString().padStart(2, '0')}:00:00`,
        });
      } else {
        // Split the slot
        newSlots.push({
          ...slot,
          end_time: `${hour.toString().padStart(2, '0')}:00:00`,
        });
        newSlots.push({
          ...slot,
          start_time: `${(hour + 1).toString().padStart(2, '0')}:00:00`,
        });
      }
    });

    return newSlots;
  };

  /**
   * Apply preset schedule to current week
   */
  const applyPresetToWeek = useCallback(
    (preset: string) => {
      const presetData = PRESET_SCHEDULES[preset];
      if (!presetData) {
        logger.error('Invalid preset selected', null, { preset });
        return;
      }

      logger.info('Applying preset schedule', { preset });

      const newSchedule: WeekSchedule = {};
      weekDates.forEach((dateInfo) => {
        const daySlots = presetData[dateInfo.dayOfWeek];
        newSchedule[dateInfo.fullDate] = daySlots || [];
      });

      setWeekSchedule(newSchedule);
      setMessage({
        type: 'success',
        text: SUCCESS_MESSAGES.PRESET_APPLIED(
          preset.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
        ),
      });
    },
    [weekDates, setWeekSchedule, setMessage]
  );

  /**
   * Clear week schedule (preserving booked slots)
   */
  const handleClearWeek = useCallback(() => {
    logger.info('Clearing week schedule');

    // Create empty schedule preserving only booked slots
    const newSchedule: WeekSchedule = {};
    weekDates.forEach((dateInfo) => {
      newSchedule[dateInfo.fullDate] = [];
    });

    setWeekSchedule(newSchedule);
    setShowClearConfirm(false);

    const bookedCount = bookedSlots.length;
    setMessage({
      type: 'info',
      text:
        bookedCount > 0
          ? `Week cleared except for ${bookedCount} slot(s) with bookings. Remember to save!`
          : 'Week cleared. Remember to save your changes.',
    });
  }, [weekDates, bookedSlots.length, setWeekSchedule, setMessage]);

  /**
   * Handle save operation
   */
  const handleSave = useCallback(async () => {
    logger.info('Save operation started', {
      time: new Date().toISOString(),
      weekStart: currentWeekStart.toISOString(),
    });

    const result = await saveWeekSchedule();

    if (result.success) {
      setMessage({ type: 'success', text: result.message });

      logger.debug('Refreshing schedule after save');
      await refreshSchedule();

      logger.info('Save completed', {
        hasUnsavedChanges,
        weekScheduleKeys: Object.keys(weekSchedule),
        savedWeekScheduleKeys: Object.keys(savedWeekSchedule),
      });
    } else {
      logger.error('Save failed', null, { message: result.message });
      setMessage({ type: 'error', text: result.message });
    }
  }, [
    saveWeekSchedule,
    setMessage,
    refreshSchedule,
    weekSchedule,
    savedWeekSchedule,
    hasUnsavedChanges,
    currentWeekStart,
  ]);

  /**
   * Handle copy from previous week
   */
  const handleCopyPrevious = useCallback(async () => {
    const result = await copyFromPreviousWeek();
    if (result.success) {
      // Don't refresh from backend - we want to keep it as unsaved changes
      setMessage({ type: 'success', text: result.message });
    } else {
      setMessage({ type: 'error', text: result.message });
    }
  }, [copyFromPreviousWeek, setMessage]);

  /**
   * Handle apply to future weeks
   */
  const handleApplyToFuture = useCallback(
    async (endDate: string) => {
      const result = await applyToFutureWeeks(endDate);
      if (result.success) {
        setMessage({ type: 'success', text: result.message });
      } else {
        setMessage({ type: 'error', text: result.message });
      }
      setShowApplyModal(false);
    },
    [applyToFutureWeeks, setMessage]
  );

  /**
   * Cell renderer for desktop calendar grid
   */
  const renderCell = (date: string, hour: number) => {
    const isPastSlot = isTimeSlotInPast(date, hour);
    const isAvailable =
      weekSchedule[date]?.some((slot) => {
        const startHour = parseInt(slot.start_time.split(':')[0]);
        const endHour = parseInt(slot.end_time.split(':')[0]);
        return hour >= startHour && hour < endHour;
      }) || false;

    const booking = getBookingForSlot(date, hour);
    const isBooked = !!booking;
    const isFirstSlot = !!(booking && parseInt(booking.start_time.split(':')[0]) === hour);

    if (isBooked && booking) {
      return (
        <BookedSlotCell
          slot={booking}
          isFirstSlot={isFirstSlot}
          onClick={() => handleBookingClick(booking.booking_id)}
        />
      );
    }

    return (
      <TimeSlotButton
        hour={hour}
        isAvailable={isAvailable}
        isBooked={isBooked}
        isPast={isPastSlot}
        onClick={() => toggleTimeSlot(date, hour)}
      />
    );
  };

  /**
   * Cell renderer for mobile calendar grid
   */
  const renderMobileCell = (date: string, hour: number) => {
    const isPastSlot = isTimeSlotInPast(date, hour);
    const isAvailable =
      weekSchedule[date]?.some((slot) => {
        const startHour = parseInt(slot.start_time.split(':')[0]);
        const endHour = parseInt(slot.end_time.split(':')[0]);
        return hour >= startHour && hour < endHour;
      }) || false;

    const booking = getBookingForSlot(date, hour);
    const isBooked = !!booking;
    const isFirstSlot = !!(booking && parseInt(booking.start_time.split(':')[0]) === hour);

    if (isBooked && booking) {
      return (
        <BookedSlotCell
          key={`${date}-${hour}`}
          slot={booking}
          isFirstSlot={isFirstSlot}
          isMobile={true}
          onClick={() => handleBookingClick(booking.booking_id)}
        />
      );
    }

    return (
      <TimeSlotButton
        key={`${date}-${hour}`}
        hour={hour}
        isAvailable={isAvailable}
        isBooked={isBooked}
        isPast={isPastSlot}
        onClick={() => toggleTimeSlot(date, hour)}
        isMobile={true}
      />
    );
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* Back to Dashboard Link */}
      <Link
        href="/instructor/dashboard"
        className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-4"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Dashboard
      </Link>

      {/* Page Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Manage Your Availability</h1>
        <p className="text-gray-600">Set your schedule week by week for maximum flexibility</p>
      </div>

      {/* Message Display */}
      {message && (
        <div
          className={`mb-6 p-4 rounded-lg flex items-start gap-2 ${
            message.type === 'success'
              ? 'bg-green-50 text-green-800'
              : message.type === 'error'
                ? 'bg-red-50 text-red-800'
                : 'bg-blue-50 text-blue-800'
          }`}
        >
          <AlertCircle className="w-5 h-5 mt-0.5" />
          {message.text}
        </div>
      )}

      {/* Unsaved Changes Warning */}
      {hasUnsavedChanges && (
        <div className="mb-6 p-4 rounded-lg bg-yellow-50 text-yellow-800 flex items-start gap-2">
          <AlertCircle className="w-5 h-5 mt-0.5" />
          You have unsaved changes for this week. Don&apos;t forget to save!
        </div>
      )}

      {/* Week Navigation */}
      <WeekNavigator
        currentWeekStart={currentWeekStart}
        onNavigate={navigateWeek}
        hasUnsavedChanges={hasUnsavedChanges}
      />

      {/* Action Buttons */}
      <ActionButtons
        onSave={handleSave}
        onCopyPrevious={handleCopyPrevious}
        onApplyFuture={() => setShowApplyModal(true)}
        isSaving={isSaving}
        isValidating={isValidating}
        hasUnsavedChanges={hasUnsavedChanges}
      />

      {/* Preset Buttons */}
      <PresetButtons
        onPresetSelect={applyPresetToWeek}
        onClearWeek={() => setShowClearConfirm(true)}
        disabled={isSaving}
      />

      {/* Weekly Calendar Grid */}
      <WeekCalendarGrid
        weekDates={weekDates}
        startHour={8}
        endHour={20}
        renderCell={renderCell}
        renderMobileCell={renderMobileCell}
        currentWeekDisplay={currentWeekDisplay}
      />

      {/* Instructions */}
      <InstructionsCard />

      {/* Modals */}
      <ClearWeekConfirmModal
        isOpen={showClearConfirm}
        onClose={() => setShowClearConfirm(false)}
        onConfirm={handleClearWeek}
        bookedSlotsCount={bookedSlots.length}
      />

      <ApplyToFutureWeeksModal
        isOpen={showApplyModal}
        onClose={() => setShowApplyModal(false)}
        onConfirm={handleApplyToFuture}
        hasAvailability={Object.keys(weekSchedule).some((date) => weekSchedule[date].length > 0)}
        currentWeekStart={currentWeekStart}
      />

      <ValidationPreviewModal
        isOpen={showValidationPreview}
        validationResults={validationResults}
        onClose={() => setShowValidationPreview(false)}
        onConfirm={() => saveWeekSchedule({ skipValidation: true })}
        isSaving={isSaving}
      />

      {/* Booking Preview Modal */}
      {showBookingPreview && selectedBookingId && (
        <BookingQuickPreview
          bookingId={selectedBookingId}
          onClose={closeBookingPreview}
          onViewFullDetails={() => {
            router.push(`/instructor/bookings/${selectedBookingId}`);
          }}
        />
      )}
    </div>
  );
}
