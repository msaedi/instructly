// frontend/components/modals/ManageAvailability.tsx
'use client';

import { useState, useEffect } from 'react';
import { Calendar, Clock, Trash2, Plus, AlertCircle, Info } from 'lucide-react';
import Modal from '@/components/Modal';
import { fetchWithAuth } from '@/lib/api';
import { logger } from '@/lib/logger';
import { TimeSlot } from '@/types/availability';

/**
 * ManageAvailability Component
 *
 * DEPRECATED: This component is from the old date-based availability system.
 * Updated with professional design for consistency.
 *
 * @deprecated Use the week-based availability management instead
 * @component
 */
interface AvailabilityManagerProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal should close */
  onClose: () => void;
}

/**
 * Extended TimeSlot interface for this component
 */
interface ExtendedTimeSlot extends TimeSlot {
  /** Unique identifier for the slot */
  id?: number;
  /** Whether the slot is booked */
  is_booked?: boolean;
}

export default function ManageAvailability({ isOpen, onClose }: AvailabilityManagerProps) {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [timeSlots, setTimeSlots] = useState<ExtendedTimeSlot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [newSlotStart, setNewSlotStart] = useState('09:00');
  const [newSlotEnd, setNewSlotEnd] = useState('10:00');

  /**
   * Generate time options for dropdowns (6 AM to 10 PM in 30-minute intervals)
   */
  const generateTimeOptions = () => {
    const options = [];
    for (let hour = 6; hour <= 22; hour++) {
      for (let minute = 0; minute < 60; minute += 30) {
        const time = `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
        options.push(time);
      }
    }
    return options;
  };

  const timeOptions = generateTimeOptions();

  useEffect(() => {
    if (isOpen && selectedDate) {
      logger.debug('Manage availability modal opened', { selectedDate });
      fetchTimeSlots();
    }
  }, [isOpen, selectedDate]);

  /**
   * Fetch time slots for the selected date
   */
  const fetchTimeSlots = async () => {
    setLoading(true);
    logger.info('Fetching time slots', { date: selectedDate });

    try {
      const response = await fetchWithAuth(`/instructors/availability?date=${selectedDate}`);

      if (!response.ok) {
        throw new Error('Failed to fetch time slots');
      }

      const data = await response.json();
      logger.debug('Time slots loaded', {
        date: selectedDate,
        slotsCount: data.length,
      });
      setTimeSlots(data);
    } catch (err) {
      logger.error('Failed to load availability', err, { date: selectedDate });
      setError('Failed to load availability');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Add a new time slot for the selected date
   */
  const addTimeSlot = async () => {
    if (newSlotStart >= newSlotEnd) {
      logger.warn('Invalid time slot attempt', {
        start: newSlotStart,
        end: newSlotEnd,
      });
      setError('End time must be after start time');
      return;
    }

    setLoading(true);
    setError('');

    logger.info('Adding new time slot', {
      date: selectedDate,
      start: newSlotStart,
      end: newSlotEnd,
    });

    try {
      // Create date strings with timezone offset
      const startDateTime = new Date(`${selectedDate}T${newSlotStart}:00`);
      const endDateTime = new Date(`${selectedDate}T${newSlotEnd}:00`);

      const response = await fetchWithAuth('/instructors/availability', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          start_time: startDateTime.toISOString(),
          end_time: endDateTime.toISOString(),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to add time slot');
      }

      logger.info('Time slot added successfully');
      await fetchTimeSlots();
    } catch (err: any) {
      logger.error('Failed to add time slot', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Delete a time slot
   */
  const deleteTimeSlot = async (slotId: number) => {
    logger.info('Deleting time slot', { slotId });

    try {
      const response = await fetchWithAuth(`/instructors/availability/${slotId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete time slot');
      }

      logger.info('Time slot deleted successfully', { slotId });
      await fetchTimeSlots();
    } catch (err) {
      logger.error('Failed to delete time slot', err, { slotId });
      setError('Failed to delete time slot');
    }
  };

  /**
   * Toggle availability status of a time slot
   */
  const toggleAvailability = async (slotId: number, currentStatus: boolean) => {
    logger.info('Toggling time slot availability', {
      slotId,
      currentStatus,
      newStatus: !currentStatus,
    });

    try {
      const response = await fetchWithAuth(`/instructors/availability/${slotId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          is_available: !currentStatus,
        }),
      });

      if (!response.ok) {
        if (response.status === 400) {
          const error = await response.json();
          throw new Error(error.detail || 'Cannot change availability of booked time slots');
        }
        throw new Error('Failed to update availability');
      }

      logger.info('Availability toggled successfully', { slotId });
      await fetchTimeSlots();
    } catch (err: any) {
      logger.error('Failed to update availability', err, { slotId });
      setError(err.message || 'Failed to update availability');
    }
  };

  /**
   * Generate next 30 days for date selection
   */
  const generateDateOptions = () => {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 30; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      dates.push(date.toISOString().split('T')[0]);
    }
    return dates;
  };

  if (!isOpen) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Manage Availability (Legacy)"
      size="lg"
      footer={
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-amber-600">
            <Info className="w-4 h-4" />
            <p className="text-sm">
              This is the old availability system. Use the week-based calendar instead.
            </p>
          </div>
          <button
            onClick={() => {
              logger.debug('Manage availability modal closed from footer');
              onClose();
            }}
            className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg
                     hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                     focus:ring-gray-500 transition-all duration-150 font-medium"
          >
            Close
          </button>
        </div>
      }
    >
      <div className="space-y-6">
        {/* Deprecation Notice */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm text-amber-900 font-medium">This system is deprecated</p>
            <p className="text-sm text-amber-700 mt-1">
              Please use the new week-based availability management for better functionality.
            </p>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Date Selection */}
        <div>
          <label htmlFor="date-select" className="block text-sm font-medium text-gray-700 mb-2">
            Select Date
          </label>
          <select
            id="date-select"
            value={selectedDate}
            onChange={(e) => {
              logger.debug('Date changed', { newDate: e.target.value });
              setSelectedDate(e.target.value);
            }}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                     focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          >
            {generateDateOptions().map((date) => (
              <option key={date} value={date}>
                {new Date(date + 'T00:00:00').toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </option>
            ))}
          </select>
        </div>

        {/* Add New Time Slot */}
        <div className="p-4 bg-gray-50 rounded-lg">
          <h3 className="text-sm font-medium text-gray-900 mb-3">Add New Time Slot</h3>
          <div className="flex items-end gap-4">
            <div className="flex-1">
              <label htmlFor="slot-start" className="block text-xs text-gray-600 mb-1">
                Start Time
              </label>
              <select
                id="slot-start"
                value={newSlotStart}
                onChange={(e) => setNewSlotStart(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                {timeOptions.map((time) => (
                  <option key={time} value={time}>
                    {time}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label htmlFor="slot-end" className="block text-xs text-gray-600 mb-1">
                End Time
              </label>
              <select
                id="slot-end"
                value={newSlotEnd}
                onChange={(e) => setNewSlotEnd(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none
                         focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                {timeOptions.map((time) => (
                  <option key={time} value={time}>
                    {time}
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={addTimeSlot}
              disabled={loading}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700
                       disabled:opacity-50 disabled:cursor-not-allowed flex items-center
                       gap-2 transition-all duration-150 font-medium focus:outline-none
                       focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
            >
              <Plus className="w-4 h-4" />
              Add Slot
            </button>
          </div>
        </div>

        {/* Time Slots List */}
        <div>
          <h3 className="text-sm font-medium text-gray-900 mb-3">
            Time Slots for {new Date(selectedDate + 'T00:00:00').toLocaleDateString()}
          </h3>
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-indigo-600 border-t-transparent mx-auto"></div>
              <p className="mt-3 text-sm text-gray-500">Loading slots...</p>
            </div>
          ) : timeSlots.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Clock className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>No time slots for this date</p>
              <p className="text-sm mt-1">Add some above to get started!</p>
            </div>
          ) : (
            <div className="space-y-2">
              {timeSlots.map((slot) => (
                <div
                  key={slot.id}
                  className={`flex items-center justify-between p-4 rounded-lg border transition-colors ${
                    slot.is_booked
                      ? 'bg-red-50 border-red-200'
                      : slot.is_available
                        ? 'bg-green-50 border-green-200'
                        : 'bg-gray-50 border-gray-200'
                  }`}
                >
                  <div className="flex items-center gap-4">
                    <Clock className="w-5 h-5 text-gray-400" />
                    <div>
                      <span className="font-medium text-gray-900">
                        {new Date(slot.start_time).toLocaleTimeString('en-US', {
                          hour: 'numeric',
                          minute: '2-digit',
                          timeZone: 'America/New_York',
                        })}
                        {' - '}
                        {new Date(slot.end_time).toLocaleTimeString('en-US', {
                          hour: 'numeric',
                          minute: '2-digit',
                          timeZone: 'America/New_York',
                        })}
                      </span>
                      <span
                        className={`ml-3 px-2 py-1 rounded-full text-xs font-medium ${
                          slot.is_booked
                            ? 'bg-red-100 text-red-800'
                            : slot.is_available
                              ? 'bg-green-100 text-green-800'
                              : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {slot.is_booked
                          ? 'Booked'
                          : slot.is_available
                            ? 'Available'
                            : 'Unavailable'}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() =>
                        slot.id && !slot.is_booked && toggleAvailability(slot.id, slot.is_available)
                      }
                      className={`text-sm font-medium ${
                        slot.is_booked
                          ? 'text-gray-400 cursor-not-allowed'
                          : 'text-indigo-600 hover:text-indigo-700 cursor-pointer transition-colors'
                      }`}
                      disabled={slot.is_booked}
                    >
                      {slot.is_booked
                        ? 'Booked'
                        : slot.is_available
                          ? 'Mark Unavailable'
                          : 'Mark Available'}
                    </button>
                    <button
                      onClick={() => slot.id && !slot.is_booked && deleteTimeSlot(slot.id)}
                      className={`p-1.5 rounded transition-colors ${
                        slot.is_booked
                          ? 'text-gray-300 cursor-not-allowed'
                          : 'text-red-600 hover:text-red-700 hover:bg-red-50'
                      }`}
                      disabled={slot.is_booked}
                      aria-label="Delete time slot"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
