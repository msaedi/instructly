// components/ManageAvailability.tsx
"use client";

import { useState, useEffect } from "react";
import { Calendar, Clock, Trash2, Plus } from "lucide-react";
import { fetchWithAuth } from '@/lib/api';

interface TimeSlot {
  id?: number;
  start_time: string;
  end_time: string;
  is_available: boolean;
  is_booked?: boolean;
}

interface AvailabilityManagerProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function ManageAvailability({ isOpen, onClose }: AvailabilityManagerProps) {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [timeSlots, setTimeSlots] = useState<TimeSlot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [newSlotStart, setNewSlotStart] = useState("09:00");
  const [newSlotEnd, setNewSlotEnd] = useState("10:00");

  // Generate time options for dropdowns
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
      fetchTimeSlots();
    }
  }, [isOpen, selectedDate]);

  const fetchTimeSlots = async () => {
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/instructors/availability?date=${selectedDate}`);

      if (!response.ok) throw new Error("Failed to fetch time slots");

      const data = await response.json();
      setTimeSlots(data);
    } catch (err) {
      setError("Failed to load availability");
    } finally {
      setLoading(false);
    }
  };

  const addTimeSlot = async () => {
    if (newSlotStart >= newSlotEnd) {
      setError("End time must be after start time");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const token = localStorage.getItem("access_token");
      
      // Create date strings with timezone offset
      const startDateTime = new Date(`${selectedDate}T${newSlotStart}:00`);
      const endDateTime = new Date(`${selectedDate}T${newSlotEnd}:00`);
      
      const response = await fetchWithAuth('/instructors/availability', {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          start_time: startDateTime.toISOString(),
          end_time: endDateTime.toISOString(),
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to add time slot");
      }

      await fetchTimeSlots();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteTimeSlot = async (slotId: number) => {
    try {
      const response = await fetchWithAuth(`/instructors/availability/${slotId}`, {
        method: "DELETE",
      });

      if (!response.ok) throw new Error("Failed to delete time slot");

      await fetchTimeSlots();
    } catch (err) {
      setError("Failed to delete time slot");
    }
  };

  const toggleAvailability = async (slotId: number, currentStatus: boolean) => {
    try {
      const response = await fetchWithAuth(`/instructors/availability/${slotId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          is_available: !currentStatus,
        }),
      });
  
      if (!response.ok) {
        if (response.status === 400) {
          const error = await response.json();
          throw new Error(error.detail || "Cannot change availability of booked time slots");
        }
        throw new Error("Failed to update availability");
      }
  
      await fetchTimeSlots();
    } catch (err: any) {
      setError(err.message || "Failed to update availability");
    }
  };

  // Generate next 30 days for date selection
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
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden">
        <div className="flex justify-between items-center p-6 border-b">
          <h2 className="text-2xl font-bold flex items-center">
            <Calendar className="mr-2" size={24} />
            Manage Availability
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
          {error && (
            <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
              {error}
            </div>
          )}

          {/* Date Selection */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Date
            </label>
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
          <div className="mb-6 p-4 bg-gray-50 rounded-lg">
            <h3 className="text-lg font-semibold mb-3">Add New Time Slot</h3>
            <div className="flex items-end gap-4">
              <div className="flex-1">
                <label className="block text-sm text-gray-600 mb-1">Start Time</label>
                <select
                  value={newSlotStart}
                  onChange={(e) => setNewSlotStart(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {timeOptions.map((time) => (
                    <option key={time} value={time}>{time}</option>
                  ))}
                </select>
              </div>
              <div className="flex-1">
                <label className="block text-sm text-gray-600 mb-1">End Time</label>
                <select
                  value={newSlotEnd}
                  onChange={(e) => setNewSlotEnd(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {timeOptions.map((time) => (
                    <option key={time} value={time}>{time}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={addTimeSlot}
                disabled={loading}
                className="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50 flex items-center"
              >
                <Plus size={16} className="mr-1" />
                Add Slot
              </button>
            </div>
          </div>

          {/* Time Slots List */}
          <div>
            <h3 className="text-lg font-semibold mb-3">Time Slots for {new Date(selectedDate + 'T00:00:00').toLocaleDateString()}</h3>
            {loading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
              </div>
            ) : timeSlots.length === 0 ? (
              <p className="text-gray-500 text-center py-8">No time slots for this date. Add some above!</p>
            ) : (
              <div className="space-y-2">
                {timeSlots.map((slot) => (
                  <div
                    key={slot.id}
                    className={`flex items-center justify-between p-3 rounded-lg border ${
                      slot.is_available
                        ? 'bg-green-50 border-green-200'
                        : 'bg-gray-50 border-gray-200'
                    }`}
                  >
                    <div className="flex items-center">
                      <Clock size={20} className="mr-2 text-gray-600" />
                      <span className="font-medium">
                        {new Date(slot.start_time).toLocaleTimeString('en-US', {
                          hour: 'numeric',
                          minute: '2-digit',
                          timeZone: 'America/New_York'
                        })}
                        {' - '}
                        {new Date(slot.end_time).toLocaleTimeString('en-US', {
                          hour: 'numeric',
                          minute: '2-digit',
                          timeZone: 'America/New_York'
                        })}
                      </span>
                      <span className={`ml-4 px-2 py-1 rounded text-sm ${
                        slot.is_booked
                          ? 'bg-red-100 text-red-800'
                          : slot.is_available
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        {slot.is_booked ? 'Booked' : (slot.is_available ? 'Available' : 'Unavailable')}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => slot.id && !slot.is_booked && toggleAvailability(slot.id, slot.is_available)}
                        className={`text-sm ${
                          slot.is_booked 
                            ? 'text-gray-400 cursor-not-allowed' 
                            : 'text-indigo-600 hover:text-indigo-700 cursor-pointer'
                        }`}
                        disabled={slot.is_booked}
                      >
                        {slot.is_booked ? 'Booked' : (slot.is_available ? 'Mark Unavailable' : 'Mark Available')}
                      </button>
                      <button
                        onClick={() => slot.id && !slot.is_booked && deleteTimeSlot(slot.id)}
                        className={`${
                          slot.is_booked 
                            ? 'text-gray-300 cursor-not-allowed' 
                            : 'text-red-600 hover:text-red-700'
                        }`}
                        disabled={slot.is_booked}
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="p-6 border-t bg-gray-50">
          <div className="flex justify-between items-center">
            <p className="text-sm text-gray-600">
              💡 Tip: Add your regular weekly availability, then mark specific slots as unavailable when needed.
            </p>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}