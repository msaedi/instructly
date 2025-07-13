'use client';

import { useSearchParams, useRouter } from 'next/navigation';
import { useEffect, useState, Suspense } from 'react';
import Link from 'next/link';
import { protectedApi } from '@/features/shared/api/client';
import type { Booking } from '@/types/booking';

function BookingConfirmationContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const bookingId = searchParams.get('bookingId');

  const [booking, setBooking] = useState<Booking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchBooking = async () => {
      if (!bookingId) {
        setError('No booking ID provided');
        setLoading(false);
        return;
      }

      try {
        const response = await protectedApi.getBooking(bookingId);
        if (response.error) {
          throw new Error(response.error);
        }
        if (response.data) {
          setBooking(response.data as any);
        }
      } catch (err) {
        setError('Failed to load booking details');
      } finally {
        setLoading(false);
      }
    };

    fetchBooking();
  }, [bookingId]);

  const generateICSFile = () => {
    if (!booking) return;

    const startDateTime = new Date(`${booking.booking_date}T${booking.start_time}`);
    const endDateTime = new Date(`${booking.booking_date}T${booking.end_time}`);

    const formatDate = (date: Date) => {
      return date
        .toISOString()
        .replace(/[-:]/g, '')
        .replace(/\.\d{3}/, '');
    };

    const icsContent = `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//InstaInstru//Booking//EN
BEGIN:VEVENT
UID:${booking.id}@instainstru.com
DTSTAMP:${formatDate(new Date())}
DTSTART:${formatDate(startDateTime)}
DTEND:${formatDate(endDateTime)}
SUMMARY:${(booking.service as any)?.skill || `Service #${booking.service_id}`} Lesson with ${
      (booking.instructor as any)?.user?.full_name ||
      (booking.instructor as any)?.full_name ||
      `Instructor #${booking.instructor_id}`
    }
DESCRIPTION:Booking ID: ${booking.id}\\nService: ${
      (booking.service as any)?.skill || `Service #${booking.service_id}`
    }\\nInstructor: ${
      (booking.instructor as any)?.user?.full_name ||
      (booking.instructor as any)?.full_name ||
      `Instructor #${booking.instructor_id}`
    }\\nPrice: $${booking.total_price}${
      booking.student_note ? `\\nNote: ${booking.student_note}` : ''
    }
LOCATION:${getLocationDisplay()}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR`;

    const blob = new Blob([icsContent], { type: 'text/calendar' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `instainstru-booking-${booking.id}.ics`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const getLocationDisplay = () => {
    if (!booking) return '';

    switch (booking.location_type) {
      case 'student_home':
        return "Student's Home";
      case 'instructor_location':
        return "Instructor's Location";
      case 'neutral':
        return booking.meeting_location || 'Neutral Location';
      default:
        return 'To be determined';
    }
  };

  const formatTime = (time: string) => {
    const [hours, minutes] = time.split(':');
    const hour = parseInt(hours);
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return `${displayHour}:${minutes} ${ampm}`;
  };

  const formatDate = (date: string) => {
    return new Date(date + 'T00:00:00').toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading booking details...</p>
        </div>
      </div>
    );
  }

  if (error || !booking) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <p className="text-red-600 dark:text-red-400 mb-4">{error || 'Booking not found'}</p>
          <Link
            href="/dashboard/student/bookings"
            className="text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
          >
            Go to My Bookings
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8">
        <div className="text-center mb-8">
          <div className="mx-auto w-16 h-16 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center mb-4">
            <svg
              className="w-8 h-8 text-green-600 dark:text-green-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            Booking Confirmed!
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Your lesson has been successfully booked
          </p>
        </div>

        <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
          <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-white">
            Booking Details
          </h2>

          <div className="space-y-4">
            <div className="flex items-start">
              <div className="w-20 h-20 bg-gray-200 dark:bg-gray-700 rounded-lg mr-4 flex items-center justify-center">
                <span className="text-2xl">👤</span>
              </div>
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-white">
                  {(booking.instructor as any)?.user?.full_name ||
                    (booking.instructor as any)?.full_name ||
                    `Instructor #${booking.instructor_id}`}
                </h3>
                <p className="text-gray-600 dark:text-gray-400">
                  {(booking.service as any)?.skill || `Service #${booking.service_id}`}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Date</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {formatDate(booking.booking_date)}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Time</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {formatTime(booking.start_time)} - {formatTime(booking.end_time)}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Duration</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {(() => {
                    const [startHours, startMinutes] = booking.start_time.split(':').map(Number);
                    const [endHours, endMinutes] = booking.end_time.split(':').map(Number);
                    const totalMinutes =
                      endHours * 60 + endMinutes - (startHours * 60 + startMinutes);
                    const hours = Math.floor(totalMinutes / 60);
                    const minutes = totalMinutes % 60;
                    return hours > 0
                      ? `${hours}h ${minutes > 0 ? `${minutes}m` : ''}`
                      : `${minutes}m`;
                  })()}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Price</p>
                <p className="font-medium text-gray-900 dark:text-white">${booking.total_price}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Location</p>
                <p className="font-medium text-gray-900 dark:text-white">{getLocationDisplay()}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500 dark:text-gray-400">Booking Reference</p>
                <p className="font-medium text-gray-900 dark:text-white">#{booking.id}</p>
              </div>
            </div>

            {booking.student_note && (
              <div className="mt-4">
                <p className="text-sm text-gray-500 dark:text-gray-400">Your Note</p>
                <p className="text-gray-900 dark:text-white">{booking.student_note}</p>
              </div>
            )}
          </div>
        </div>

        <div className="mt-8 space-y-3">
          <button
            onClick={generateICSFile}
            className="w-full bg-indigo-600 text-white py-3 px-4 rounded-lg hover:bg-indigo-700 transition duration-200 font-medium"
          >
            Add to Calendar
          </button>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Link
              href="/dashboard/student/bookings"
              className="text-center bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 py-3 px-4 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition duration-200 font-medium"
            >
              View My Bookings
            </Link>
            <Link
              href="/search"
              className="text-center bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 py-3 px-4 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition duration-200 font-medium"
            >
              Book Another Session
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function BookingConfirmationPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
            <p className="mt-4 text-gray-600 dark:text-gray-400">Loading booking details...</p>
          </div>
        </div>
      }
    >
      <BookingConfirmationContent />
    </Suspense>
  );
}
