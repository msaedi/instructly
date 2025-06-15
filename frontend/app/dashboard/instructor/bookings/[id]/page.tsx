// frontend/app/dashboard/instructor/bookings/[id]/page.tsx
"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { Booking } from '@/types/booking';

export default function BookingDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const bookingId = params.id as string;
  
  const [booking, setBooking] = useState<Booking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  useEffect(() => {
    fetchBookingDetails();
  }, [bookingId]);
  
  const fetchBookingDetails = async () => {
    try {
      const response = await fetchWithAuth(`${API_ENDPOINTS.BOOKINGS}/${bookingId}`);
      
      if (!response.ok) {
        throw new Error('Failed to fetch booking details');
      }
      
      const data = await response.json();
      setBooking(data);
    } catch (err) {
      setError('Failed to load booking details');
      console.error('Error fetching booking:', err);
    } finally {
      setLoading(false);
    }
  };
  
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }
  
  if (error || !booking) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center">
          <p className="text-red-600">{error || 'Booking not found'}</p>
          <Link 
            href="/dashboard/instructor/availability" 
            className="mt-4 inline-flex items-center text-blue-600 hover:text-blue-800"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Schedule
          </Link>
        </div>
      </div>
    );
  }
  
  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link 
        href="/dashboard/instructor/availability" 
        className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-4"
      >
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Schedule
      </Link>
      
      {/* Basic booking info for now - can be enhanced with A-Team's full design later */}
      <div className="bg-white rounded-lg shadow">
        {/* Header */}
        <div className="border-b px-6 py-4">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold">Booking #{booking.id}</h1>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              booking.status === 'CONFIRMED' ? 'bg-green-100 text-green-800' :
              booking.status === 'COMPLETED' ? 'bg-gray-100 text-gray-800' :
              booking.status === 'CANCELLED' ? 'bg-red-100 text-red-800' :
              'bg-yellow-100 text-yellow-800'
            }`}>
              {booking.status}
            </span>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Service Info */}
          <div className="bg-blue-50 rounded-lg p-4">
            <h2 className="font-semibold text-lg text-blue-900 mb-2">
              {booking.service_name}
            </h2>
            <div className="text-blue-700">
              Duration: {(booking as any).duration_minutes || 60} minutes
            </div>
            <div className="text-blue-700">
              Total: ${(booking as any).total_price || '0.00'}
            </div>
          </div>

          {/* Date and Time */}
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <h3 className="font-medium text-gray-900">Date</h3>
              <p className="text-gray-600">
                {new Date(booking.booking_date).toLocaleDateString('en-US', {
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric'
                })}
              </p>
            </div>
            <div>
              <h3 className="font-medium text-gray-900">Time</h3>
              <p className="text-gray-600">
                {booking.start_time} - {booking.end_time}
              </p>
            </div>
          </div>

          {/* Location */}
          <div>
            <h3 className="font-medium text-gray-900">Location</h3>
            <p className="text-gray-600">
              {(booking as any).location_type === 'student_home' ? '🏠' :
               (booking as any).location_type === 'instructor_location' ? '🏫' : '📍'}
              {' '}
              {(booking as any).meeting_location || 'Location details will be provided'}
            </p>
          </div>

          {/* Student Info */}
          <div className="border-t pt-6">
            <h3 className="font-medium text-gray-900">Student</h3>
            <p className="text-lg text-gray-800">
              {booking.student?.full_name || `Student #${booking.student_id}`}
            </p>
            <p className="text-gray-600 text-sm">
              {booking.student?.email}
            </p>
          </div>

          {/* Notes */}
          {(booking as any).student_note && (
            <div className="border-t pt-6">
              <h3 className="font-medium text-gray-900 mb-2">Note from student</h3>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-gray-700 italic">"{(booking as any).student_note}"</p>
              </div>
            </div>
          )}

          {/* Action Buttons - placeholder for now */}
          <div className="border-t pt-6 space-y-3">
            <button className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
              Mark as Complete
            </button>
            <div className="grid grid-cols-2 gap-3">
              <button className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                Reschedule
              </button>
              <button className="px-4 py-2 border border-red-300 text-red-700 rounded-lg hover:bg-red-50 transition-colors">
                Cancel Booking
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}