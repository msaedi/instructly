'use client';

import React from 'react';
import { Calendar, Clock, MapPin, AlertCircle, CreditCard, Zap } from 'lucide-react';
import { BookingPayment, PaymentMethod, BookingType } from '../types';
import { format, addHours } from 'date-fns';

interface PaymentConfirmationProps {
  booking: BookingPayment;
  paymentMethod: PaymentMethod;
  cardLast4?: string;
  creditsUsed?: number;
  onConfirm: () => void;
  onBack: () => void;
}

export default function PaymentConfirmation({
  booking,
  paymentMethod,
  cardLast4,
  creditsUsed = 0,
  onConfirm,
  onBack,
}: PaymentConfirmationProps) {
  const isLastMinute = booking.bookingType === BookingType.LAST_MINUTE;
  const cardCharge = booking.totalAmount - creditsUsed;
  const chargeDate = isLastMinute ? new Date() : addHours(booking.date, -24);

  const renderPaymentTimeline = () => {
    if (isLastMinute) {
      return (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-center mb-2">
            <Zap className="text-red-600 dark:text-red-400 mr-2" size={20} />
            <h3 className="font-semibold text-red-900 dark:text-red-100">Last-Minute Booking</h3>
          </div>
          <p className="text-sm text-red-800 dark:text-red-200">
            Your card will be charged immediately
          </p>
        </div>
      );
    }

    return (
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <h3 className="font-semibold mb-3">When you'll be charged:</h3>
        <div className="flex items-center justify-between text-sm">
          <div className="text-center">
            <p className="font-medium">Today</p>
            <p className="text-gray-600 dark:text-gray-400">(Now)</p>
            <p className="mt-1">↓</p>
            <p className="bg-blue-100 dark:bg-blue-800 px-2 py-1 rounded">Hold</p>
            <p className="text-xs mt-1">Reserve</p>
          </div>
          <div className="flex-1 border-t-2 border-dashed border-gray-300 dark:border-gray-600 mx-2"></div>
          <div className="text-center">
            <p className="font-medium">{format(chargeDate, 'MMM d')}</p>
            <p className="text-gray-600 dark:text-gray-400">{format(chargeDate, 'h:mm a')}</p>
            <p className="mt-1">↓</p>
            <p className="bg-[#FFD700] px-2 py-1 rounded">Charge</p>
            <p className="text-xs mt-1">Pay</p>
          </div>
          <div className="flex-1 border-t-2 border-dashed border-gray-300 dark:border-gray-600 mx-2"></div>
          <div className="text-center">
            <p className="font-medium">{format(booking.date, 'MMM d')}</p>
            <p className="text-gray-600 dark:text-gray-400">{booking.startTime}</p>
            <p className="mt-1">↓</p>
            <p className="bg-green-100 dark:bg-green-800 px-2 py-1 rounded">Lesson</p>
            <p className="text-xs mt-1">Complete</p>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h2 className="text-2xl font-bold mb-6">
        {isLastMinute ? '⚡ Confirm Payment' : 'Reserve Your Lesson'}
      </h2>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Left Column - Booking Details */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold mb-4 pb-2 border-b">Booking Details</h3>

          <div className="space-y-4">
            <div className="flex items-start">
              <div className="w-16 h-16 bg-gray-200 dark:bg-gray-700 rounded-lg mr-4"></div>
              <div>
                <h4 className="font-semibold">{booking.instructorName}</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400">★★★★★ (47 reviews)</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center text-sm">
                <Calendar size={16} className="mr-2 text-gray-500" />
                <span>{format(booking.date, 'EEEE, MMMM d, yyyy')}</span>
              </div>
              <div className="flex items-center text-sm">
                <Clock size={16} className="mr-2 text-gray-500" />
                <span>
                  {booking.startTime} - {booking.endTime}
                </span>
              </div>
              <div className="flex items-center text-sm">
                <MapPin size={16} className="mr-2 text-gray-500" />
                <span>{booking.location}</span>
              </div>
            </div>

            <div className="border-t pt-4">
              <div className="flex justify-between text-sm mb-2">
                <span>Lesson ({booking.duration} min)</span>
                <span>${booking.basePrice.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm mb-2">
                <span>Service fee (20%)</span>
                <span>${booking.serviceFee.toFixed(2)}</span>
              </div>
              {creditsUsed > 0 && (
                <div className="flex justify-between text-sm mb-2 text-green-600 dark:text-green-400">
                  <span>Credits applied</span>
                  <span>-${creditsUsed.toFixed(2)}</span>
                </div>
              )}
              <div className="border-t pt-2 mt-2">
                <div className="flex justify-between font-semibold">
                  <span>Total</span>
                  <span>${booking.totalAmount.toFixed(2)}</span>
                </div>
              </div>
            </div>

            {/* Cancellation Policy */}
            <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 text-sm">
              <h4 className="font-medium mb-1 flex items-center">
                <AlertCircle size={16} className="mr-1" />
                Cancellation Policy
              </h4>
              {isLastMinute ? (
                <ul className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
                  <li>• 12-24 hours: Platform credit only</li>
                  <li>• Less than 12 hours: No refund</li>
                </ul>
              ) : (
                <ul className="text-xs space-y-1 text-gray-600 dark:text-gray-400">
                  <li>• Free cancellation more than 24 hours before</li>
                  <li>• 12-24 hours: Platform credit</li>
                  <li>• Less than 12 hours: No refund</li>
                </ul>
              )}
            </div>

            <div className="bg-[#FFFEF5] dark:bg-gray-700 rounded-lg p-3 text-sm">
              <p className="text-gray-600 dark:text-gray-400">
                💡 Tips accepted after lesson completion
              </p>
            </div>
          </div>
        </div>

        {/* Right Column - Payment Information */}
        <div className="bg-[#FFFEF5] dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
          <h3 className="font-semibold mb-4 pb-2 border-b flex items-center">
            <CreditCard className="mr-2" size={20} />
            Payment Information
          </h3>

          {renderPaymentTimeline()}

          <div className="mt-6 space-y-4">
            {/* Payment Method Summary */}
            <div>
              <h4 className="font-medium mb-2">Payment Method</h4>
              {paymentMethod === PaymentMethod.CREDITS ? (
                <p className="text-sm">Using platform credits</p>
              ) : paymentMethod === PaymentMethod.MIXED ? (
                <div className="text-sm space-y-1">
                  <p>Credits: ${creditsUsed.toFixed(2)}</p>
                  <p>
                    Card (•••• {cardLast4}): ${cardCharge.toFixed(2)}
                  </p>
                </div>
              ) : (
                <p className="text-sm">
                  Card •••• {cardLast4}: ${cardCharge.toFixed(2)}
                </p>
              )}
            </div>

            {/* Charge Summary */}
            <div className="bg-white dark:bg-gray-700 rounded-lg p-4">
              <h4 className="font-medium mb-2">
                {isLastMinute ? 'Immediate Charge' : 'Authorization Details'}
              </h4>
              {isLastMinute ? (
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Your card will be charged ${cardCharge.toFixed(2)} immediately upon confirmation.
                </p>
              ) : (
                <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                  <p>• ${cardCharge.toFixed(2)} will be authorized now</p>
                  <p>
                    • Charged on {format(chargeDate, 'MMM d')} at {format(chargeDate, 'h:mm a')}
                  </p>
                  <p>• Free cancellation until then</p>
                </div>
              )}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="mt-6 space-y-3">
            <button
              onClick={onConfirm}
              className="w-full py-3 bg-[#FFD700] hover:bg-[#FFC700] text-black rounded-full font-medium transition-colors"
            >
              {isLastMinute
                ? `Pay Now - $${cardCharge.toFixed(2)}`
                : `Reserve Lesson - $${booking.totalAmount.toFixed(2)}`}
            </button>
            <button
              onClick={onBack}
              className="w-full py-3 border border-gray-300 dark:border-gray-600 rounded-full font-medium transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              Back to Payment Method
            </button>
          </div>

          <p className="text-xs text-center text-gray-500 dark:text-gray-400 mt-4">
            🔒 Secure payment • {!isLastMinute && 'Cancel free >24hrs'}
          </p>
        </div>
      </div>
    </div>
  );
}
