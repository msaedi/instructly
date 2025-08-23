'use client';

import React from 'react';
import { CheckCircle, Calendar, Clock, MapPin, CreditCard, Mail, ArrowRight } from 'lucide-react';
import { BookingPayment, BookingType } from '../types';
import { format } from 'date-fns';
import Link from 'next/link';

interface PaymentSuccessProps {
  booking: BookingPayment;
  confirmationNumber: string;
  cardLast4?: string;
  isPackage?: boolean;
  packageDetails?: {
    lessonsCount: number;
    expiryDate: Date;
  };
}

export default function PaymentSuccess({
  booking,
  confirmationNumber,
  cardLast4,
  isPackage = false,
  packageDetails,
}: PaymentSuccessProps) {
  const isLastMinute = booking.bookingType === BookingType.LAST_MINUTE;

  if (isPackage && packageDetails) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="max-w-md w-full">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8 text-center">
            {/* Success Icon */}
            <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="w-10 h-10 text-green-600 dark:text-green-400" />
            </div>

            <h2 className="text-2xl font-bold mb-2">Package Purchased!</h2>
            <p className="text-gray-600 dark:text-gray-400 mb-6">
              {packageDetails.lessonsCount} {booking.lessonType} Credits
              <br />
              with {booking.instructorName}
            </p>

            <div className="space-y-4 text-left bg-gray-50 dark:bg-gray-700 rounded-lg p-4 mb-6">
              <div className="flex items-center text-sm">
                <CreditCard className="w-4 h-4 mr-3 text-gray-500" />
                <span>
                  ${booking.totalAmount.toFixed(2)} charged to •••• {cardLast4}
                </span>
              </div>
              <div className="flex items-center text-sm">
                <Calendar className="w-4 h-4 mr-3 text-gray-500" />
                <span>Credits added to account</span>
              </div>
              <div className="flex items-start text-sm">
                <Clock className="w-4 h-4 mr-3 text-gray-500 mt-0.5" />
                <div>
                  <span>Valid until {format(packageDetails.expiryDate, 'MMMM d, yyyy')}</span>
                  <p className="text-xs text-gray-500 dark:text-gray-400">(6 months)</p>
                </div>
              </div>
            </div>

            <div className="bg-[#FFFEF5] dark:bg-gray-700 rounded-lg p-4 mb-6">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                💡 Book your lessons anytime within the next 6 months
              </p>
            </div>

            <div className="space-y-3">
              <Link
                href={`/instructors/${booking.instructorId}/book`}
                className="block w-full py-3 bg-[#FFD700] hover:bg-[#FFC700] text-black rounded-full font-medium transition-colors"
              >
                Book First Lesson
              </Link>
              <Link
                href="/student/dashboard/credits"
                className="block w-full py-3 border border-gray-300 dark:border-gray-600 rounded-full font-medium transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                View All Credits
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md w-full">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8 text-center">
          {/* Success Icon */}
          <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircle className="w-10 h-10 text-green-600 dark:text-green-400" />
          </div>

          <h2 className="text-2xl font-bold mb-2">
            {isLastMinute ? 'Booking Confirmed!' : 'Lesson Reserved!'}
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-2">
            Confirmation #{confirmationNumber}
          </p>

          {/* Booking Details */}
          <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 my-6 text-left">
            <h3 className="font-semibold mb-3">
              {booking.instructorName} - {booking.lessonType}
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center">
                <Calendar className="w-4 h-4 mr-2 text-gray-500" />
                <span>{format(booking.date, 'EEEE, MMMM d, yyyy')}</span>
              </div>
              <div className="flex items-center">
                <Clock className="w-4 h-4 mr-2 text-gray-500" />
                <span>
                  {booking.startTime} - {booking.endTime}
                </span>
              </div>
              <div className="flex items-center">
                <MapPin className="w-4 h-4 mr-2 text-gray-500" />
                <span>{booking.location}</span>
              </div>
            </div>
          </div>

          {/* Payment Info */}
          <div className="bg-[#FFFEF5] dark:bg-gray-700 rounded-lg p-4 mb-6 text-left">
            <div className="flex items-start text-sm">
              <CreditCard className="w-4 h-4 mr-2 mt-0.5 text-gray-500" />
              <div>
                {isLastMinute ? (
                  <p>
                    Card •••• {cardLast4} charged ${booking.totalAmount.toFixed(2)}
                  </p>
                ) : (
                  <>
                    <p>
                      Card •••• {cardLast4} will be charged ${booking.totalAmount.toFixed(2)}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      on {format(booking.freeCancellationUntil || new Date(), 'MMMM d')} at{' '}
                      {format(booking.freeCancellationUntil || new Date(), 'h:mm a')} (24hrs before)
                    </p>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Cancellation Info */}
          {!isLastMinute && booking.freeCancellationUntil && (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3 mb-6 text-sm text-left">
              <p className="text-green-800 dark:text-green-200">
                ✅ Free cancellation until {format(booking.freeCancellationUntil, 'MMMM d')} at{' '}
                {format(booking.freeCancellationUntil, 'h:mm a')}
              </p>
            </div>
          )}

          {/* Email Confirmation */}
          <div className="flex items-center justify-center text-sm text-gray-600 dark:text-gray-400 mb-6">
            <Mail className="w-4 h-4 mr-2" />
            <span>Confirmation email sent</span>
          </div>

          {/* Actions */}
          <div className="space-y-3">
            <Link
              href="/student/lessons"
              className="flex items-center justify-center w-full py-3 bg-[#FFD700] hover:bg-[#FFC700] text-black rounded-full font-medium transition-colors"
            >
              View My Lessons
              <ArrowRight className="ml-2 w-4 h-4" />
            </Link>
            <Link
              href="/search"
              className="block w-full py-3 border border-gray-300 dark:border-gray-600 rounded-full font-medium transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              Book Another Lesson
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
