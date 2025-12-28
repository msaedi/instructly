"use client";

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { ArrowLeft, Calendar, Clock, MapPin, User, DollarSign, CheckCircle, AlertTriangle } from 'lucide-react';
import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { getLocationTypeIcon, type LocationType } from '@/types/booking';
import { at } from '@/lib/ts/safe';
import { useBooking, useCompleteBooking, useMarkBookingNoShow } from '@/src/api/services/bookings';
import { queryKeys } from '@/src/api/queryKeys';

export default function BookingDetailsPage() {
  const params = useParams();
  const bookingId = params['id'] as string;
  const queryClient = useQueryClient();
  const [showNoShowModal, setShowNoShowModal] = useState(false);

  // Use React Query hook for booking details (prevents duplicate API calls)
  const { data: booking, isLoading: loading, error: queryError } = useBooking(bookingId);
  const error = queryError ? 'Failed to load booking details' : null;

  // Mutations for complete and no-show actions
  const completeBooking = useCompleteBooking();
  const markNoShow = useMarkBookingNoShow();

  const handleMarkComplete = async () => {
    try {
      await completeBooking.mutateAsync({ bookingId });
      toast.success('Lesson marked as complete', { duration: 3000 });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch {
      toast.error('Failed to mark lesson as complete', { duration: 4000 });
    }
  };

  const handleMarkNoShow = async () => {
    try {
      await markNoShow.mutateAsync({
        bookingId,
        data: { no_show_type: 'student' },
      });
      toast.success('Lesson marked as no-show', { duration: 3000 });
      setShowNoShowModal(false);
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch {
      toast.error('Failed to mark lesson as no-show', { duration: 4000 });
    }
  };

  // Check if lesson is past and needs action
  const isPastLesson = (): boolean => {
    if (!booking) return false;
    const lessonEnd = new Date(`${booking.booking_date}T${booking.end_time}`);
    return lessonEnd < new Date();
  };

  const needsAction = booking?.status === 'CONFIRMED' && isPastLesson();

  const formatTime = (timeStr: string) => {
    const parts = timeStr.split(':');
    const hours = at(parts, 0);
    const minutes = at(parts, 1);
    if (!hours || !minutes) return timeStr;
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 || 12;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'CONFIRMED':
        return 'bg-green-100 text-green-800';
      case 'COMPLETED':
        return 'bg-gray-100 text-gray-800';
      case 'CANCELLED':
        return 'bg-red-100 text-red-800';
      case 'NO_SHOW':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
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
          <p className="text-red-600 mb-4">{error || 'Booking not found'}</p>
          <Link href="/instructor/availability" className="inline-flex items-center text-blue-600 hover:text-blue-800">
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Schedule
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/instructor/availability" className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-6">
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Schedule
      </Link>

      <div className="bg-white rounded-lg shadow">
        <div className="border-b px-6 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold">Booking #{booking.id}</h1>
              <p className="text-gray-600 text-sm mt-1">Created on {new Date(booking.created_at).toLocaleDateString()}</p>
            </div>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${getStatusBadgeClass(booking.status)}`}>
              {booking.status}
            </span>
          </div>
        </div>

        <div className="p-6 space-y-6">
          <div className="bg-blue-50 rounded-lg p-4">
            <h2 className="font-semibold text-lg text-blue-900 mb-3">{booking.service_name}</h2>
            <div className="grid md:grid-cols-3 gap-4 text-sm">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-blue-600" />
                <span className="text-blue-700">Duration: {booking.duration_minutes} minutes</span>
              </div>
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-blue-600" />
                <span className="text-blue-700">Rate: ${booking.hourly_rate}/hour</span>
              </div>
              <div className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-blue-600" />
                <span className="text-blue-700 font-semibold">Total: ${booking.total_price}</span>
              </div>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Calendar className="w-4 h-4 text-gray-400" />
                <h3 className="font-medium text-gray-900">Date</h3>
              </div>
              <p className="text-gray-600">{new Date(booking.booking_date).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</p>
            </div>
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-4 h-4 text-gray-400" />
                <h3 className="font-medium text-gray-900">Time</h3>
              </div>
              <p className="text-gray-600">{formatTime(booking.start_time)} - {formatTime(booking.end_time)}</p>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-2">
              <MapPin className="w-4 h-4 text-gray-400" />
              <h3 className="font-medium text-gray-900">Location</h3>
            </div>
            <div className="text-gray-600">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">{booking.location_type ? getLocationTypeIcon(booking.location_type as LocationType) : '📍'}</span>
                <span className="font-medium">{booking.location_type === 'student_home' ? "Student's Home" : booking.location_type === 'instructor_location' ? "Instructor's Location" : 'Neutral Location'}</span>
              </div>
              {booking.meeting_location && <p className="ml-7 text-sm">{booking.meeting_location}</p>}
              {booking.service_area && <p className="ml-7 text-sm text-gray-500">Service area: {booking.service_area}</p>}
            </div>
          </div>

          <div className="border-t pt-6">
            <div className="flex items-center gap-2 mb-3">
              <User className="w-4 h-4 text-gray-400" />
              <h3 className="font-medium text-gray-900">Student Information</h3>
            </div>
            <div className="ml-6">
              <p className="text-lg text-gray-800 font-medium">{booking.student ? `${booking.student.first_name} ${booking.student.last_name}` : `Student #${booking.student_id}`}</p>
              {booking.student?.email && (<a href={`mailto:${booking.student.email}`} className="text-blue-600 hover:text-blue-800 text-sm">{booking.student.email}</a>)}
            </div>
          </div>

          {(booking.student_note || booking.instructor_note) && (
            <div className="border-t pt-6 space-y-4">
              {booking.student_note && (
                <div>
                  <h3 className="font-medium text-gray-900 mb-2">Note from student</h3>
                  <div className="bg-gray-50 rounded-lg p-4"><p className="text-gray-700 italic">&quot;{booking.student_note}&quot;</p></div>
                </div>
              )}
              {booking.instructor_note && (
                <div>
                  <h3 className="font-medium text-gray-900 mb-2">Instructor notes</h3>
                  <div className="bg-yellow-50 rounded-lg p-4"><p className="text-gray-700">{booking.instructor_note}</p></div>
                </div>
              )}
            </div>
          )}

          {booking.status === 'CANCELLED' && booking.cancellation_reason && (
            <div className="border-t pt-6">
              <h3 className="font-medium text-gray-900 mb-2">Cancellation Details</h3>
              <div className="bg-red-50 rounded-lg p-4">
                <p className="text-red-800"><span className="font-medium">Reason:</span> {booking.cancellation_reason}</p>
                {booking.cancelled_at && (<p className="text-red-600 text-sm mt-1">Cancelled on {new Date(booking.cancelled_at).toLocaleDateString()}</p>)}
              </div>
            </div>
          )}

          {/* Action buttons for past CONFIRMED lessons */}
          {needsAction && (
            <div className="border-t pt-6">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
                <div className="flex items-center gap-2 text-amber-800">
                  <AlertTriangle className="w-5 h-5" />
                  <span className="font-medium">Action Required</span>
                </div>
                <p className="text-amber-700 text-sm mt-1">
                  This lesson has ended. Please confirm the outcome.
                </p>
              </div>
              <div className="flex gap-4">
                <button
                  onClick={handleMarkComplete}
                  disabled={completeBooking.isPending || markNoShow.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <CheckCircle className="w-4 h-4" />
                  {completeBooking.isPending ? 'Marking...' : 'Mark Complete'}
                </button>
                <button
                  onClick={() => setShowNoShowModal(true)}
                  disabled={completeBooking.isPending || markNoShow.isPending}
                  className="flex items-center gap-2 px-4 py-2 border border-amber-600 text-amber-700 rounded-lg hover:bg-amber-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <AlertTriangle className="w-4 h-4" />
                  Report No-Show
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* No-Show Confirmation Modal */}
      {showNoShowModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
            <div className="mb-4">
              <div className="flex items-center gap-2 text-amber-600 mb-2">
                <AlertTriangle className="w-6 h-6" />
                <h3 className="text-lg font-semibold text-gray-900">Report No-Show</h3>
              </div>
              <p className="text-sm text-gray-600">
                Are you sure you want to mark this lesson as a no-show? This indicates that
                <span className="font-medium"> {booking.student ? `${booking.student.first_name} ${booking.student.last_name}` : 'the student'}</span> did not attend the scheduled lesson.
              </p>
              <p className="text-sm text-gray-500 mt-2">
                The student will still be charged for the lesson.
              </p>
            </div>
            <div className="flex justify-end gap-3">
              <button
                className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors"
                onClick={() => setShowNoShowModal(false)}
                disabled={markNoShow.isPending}
              >
                Cancel
              </button>
              <button
                className="rounded-lg px-4 py-2 text-sm font-medium bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                onClick={handleMarkNoShow}
                disabled={markNoShow.isPending}
              >
                {markNoShow.isPending ? 'Marking...' : 'Confirm No-Show'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
