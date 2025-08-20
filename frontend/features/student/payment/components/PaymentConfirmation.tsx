'use client';

import React, { useState } from 'react';
import { Calendar, Clock, MapPin, AlertCircle, Star, ChevronDown, ChevronUp } from 'lucide-react';
import { BookingPayment, PaymentMethod, BookingType } from '../types';
import { format } from 'date-fns';

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
  onBack, // eslint-disable-line @typescript-eslint/no-unused-vars
}: PaymentConfirmationProps) {
  const [isOnlineLesson, setIsOnlineLesson] = useState(false);
  // Auto-collapse payment if user has a saved card
  const hasSavedCard = !!cardLast4;
  const [isPaymentExpanded, setIsPaymentExpanded] = useState(!hasSavedCard);
  // Auto-collapse location if they have a saved address or it's online
  const hasSavedLocation = booking.location && booking.location !== '';
  const [isLocationExpanded, setIsLocationExpanded] = useState(!hasSavedLocation && !isOnlineLesson);
  const isLastMinute = booking.bookingType === BookingType.LAST_MINUTE;
  const cardCharge = booking.totalAmount - creditsUsed;


  return (
    <div className="p-6">
      <div className="flex gap-6">
        {/* Left Column - Confirm Details - 60% width */}
        <div className="w-[60%] bg-white dark:bg-gray-900 rounded-lg p-6 order-2 md:order-1">
          <h3 className="font-extrabold text-2xl mb-4">Confirm details</h3>

        {/* Payment Method */}
        <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setIsPaymentExpanded(!isPaymentExpanded)}
          >
            <div className="flex items-center gap-3">
              <h4 className="font-bold text-xl">Payment Method</h4>
              {!isPaymentExpanded && hasSavedCard && (
                <span className="text-sm text-gray-600">•••• {cardLast4}</span>
              )}
            </div>
            {isPaymentExpanded ? (
              <ChevronUp className="h-5 w-5 text-gray-600" />
            ) : (
              <ChevronDown className="h-5 w-5 text-gray-600" />
            )}
          </div>

          {/* Credit Card Fields */}
          {isPaymentExpanded && (
          <div className="space-y-3 mt-3">
            {hasSavedCard ? (
              <div className="bg-white p-3 rounded-lg border border-gray-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">Visa ending in {cardLast4}</span>
                    <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">Default</span>
                  </div>
                  <button className="text-sm text-purple-700 hover:text-purple-800">Change</button>
                </div>
              </div>
            ) : (
              <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Card Number
              </label>
              <input
                type="text"
                placeholder="1234 5678 9012 3456"
                className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                style={{ outline: 'none' }}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Expiry Date
                </label>
                <input
                  type="text"
                  placeholder="MM/YY"
                  className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                  style={{ outline: 'none' }}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  CVV
                </label>
                <input
                  type="text"
                  placeholder="123"
                  className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                  style={{ outline: 'none' }}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Name on Card
              </label>
              <input
                type="text"
                placeholder="John Doe"
                className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                style={{ outline: 'none' }}
              />
            </div>

            {/* Billing Address */}
            <div className="pt-3 mt-3 border-t border-gray-200">
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Billing Address
              </label>

              <div className="space-y-3">
                <div>
                  <input
                    type="text"
                    placeholder="Address"
                    className="w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />
                </div>

                <div className="grid grid-cols-6 gap-3">
                  <input
                    type="text"
                    placeholder="City"
                    className="col-span-3 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />

                  <input
                    type="text"
                    placeholder="State"
                    className="col-span-1 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />

                  <input
                    type="text"
                    placeholder="ZIP Code"
                    className="col-span-2 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                  />
                </div>

                <div>
                  <select
                    className="w-full p-2.5 border border-gray-200 rounded-lg text-sm text-gray-700 focus:border-purple-500 transition-colors"
                    style={{ outline: 'none' }}
                    defaultValue="US"
                  >
                    <option value="US">United States</option>
                    <option value="CA">Canada</option>
                    <option value="MX">Mexico</option>
                    <option value="GB">United Kingdom</option>
                    <option value="FR">France</option>
                    <option value="DE">Germany</option>
                    <option value="IT">Italy</option>
                    <option value="ES">Spain</option>
                    <option value="NL">Netherlands</option>
                    <option value="BE">Belgium</option>
                    <option value="CH">Switzerland</option>
                    <option value="AT">Austria</option>
                    <option value="SE">Sweden</option>
                    <option value="NO">Norway</option>
                    <option value="DK">Denmark</option>
                    <option value="FI">Finland</option>
                    <option value="PL">Poland</option>
                    <option value="PT">Portugal</option>
                    <option value="IE">Ireland</option>
                    <option value="CZ">Czech Republic</option>
                    <option value="GR">Greece</option>
                    <option value="RO">Romania</option>
                    <option value="HU">Hungary</option>
                    <option value="AU">Australia</option>
                    <option value="NZ">New Zealand</option>
                    <option value="JP">Japan</option>
                    <option value="KR">South Korea</option>
                    <option value="CN">China</option>
                    <option value="IN">India</option>
                    <option value="SG">Singapore</option>
                    <option value="MY">Malaysia</option>
                    <option value="TH">Thailand</option>
                    <option value="ID">Indonesia</option>
                    <option value="PH">Philippines</option>
                    <option value="VN">Vietnam</option>
                    <option value="BR">Brazil</option>
                    <option value="AR">Argentina</option>
                    <option value="CL">Chile</option>
                    <option value="CO">Colombia</option>
                    <option value="PE">Peru</option>
                    <option value="VE">Venezuela</option>
                    <option value="ZA">South Africa</option>
                    <option value="EG">Egypt</option>
                    <option value="NG">Nigeria</option>
                    <option value="KE">Kenya</option>
                    <option value="MA">Morocco</option>
                    <option value="IL">Israel</option>
                    <option value="AE">United Arab Emirates</option>
                    <option value="SA">Saudi Arabia</option>
                    <option value="TR">Turkey</option>
                    <option value="RU">Russia</option>
                    <option value="UA">Ukraine</option>
                    <option value="PK">Pakistan</option>
                    <option value="BD">Bangladesh</option>
                    <option value="LK">Sri Lanka</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex items-center mt-3">
              <input
                type="checkbox"
                id="save-card"
                className="w-4 h-4 text-purple-700 border-gray-300 rounded focus:ring-purple-500"
              />
              <label htmlFor="save-card" className="ml-2 text-sm text-gray-700">
                Save card for future payments
              </label>
            </div>

            {/* Promo Code Section */}
            <div className="mt-4 pt-4 border-t border-gray-200">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Promo Code
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Enter promo code"
                  className="flex-1 p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors"
                  style={{ outline: 'none' }}
                />
                <button
                  className="px-4 py-2.5 bg-purple-700 text-white rounded-lg text-sm font-medium hover:bg-purple-800 transition-colors"
                >
                  Apply
                </button>
              </div>
            </div>
            </>
            )}
          </div>
          )}

          {isPaymentExpanded && (
            <>
            {paymentMethod === PaymentMethod.CREDITS ? (
              <p className="text-sm mt-3">Using platform credits</p>
            ) : paymentMethod === PaymentMethod.MIXED ? (
              <div className="text-sm space-y-1 mt-3">
                <p>Credits: ${creditsUsed.toFixed(2)}</p>
                <p>
                  Card amount: ${cardCharge.toFixed(2)}
                </p>
              </div>
            ) : null}
            </>
          )}
        </div>

        {/* Lesson Location */}
        <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setIsLocationExpanded(!isLocationExpanded)}
          >
            <div className="flex items-center gap-3">
              <h4 className="font-bold text-xl">Lesson Location</h4>
              {!isLocationExpanded && (
                <span className="text-sm text-gray-600">
                  {isOnlineLesson ? 'Online' : hasSavedLocation ? booking.location : ''}
                </span>
              )}
            </div>
            {isLocationExpanded ? (
              <ChevronUp className="h-5 w-5 text-gray-600" />
            ) : (
              <ChevronDown className="h-5 w-5 text-gray-600" />
            )}
          </div>

          {/* Online Checkbox */}
          {isLocationExpanded && (
          <div className="mt-3">
          {hasSavedLocation && !isOnlineLesson ? (
            <div className="bg-white p-3 rounded-lg border border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium">{booking.location}</span>
                  <p className="text-xs text-gray-500 mt-1">Saved address</p>
                </div>
                <button className="text-sm text-purple-700 hover:text-purple-800">Change</button>
              </div>
            </div>
          ) : (
            <>
          <div className="flex items-center mb-4">
            <input
              type="checkbox"
              id="online-lesson"
              checked={isOnlineLesson}
              onChange={(e) => setIsOnlineLesson(e.target.checked)}
              className="w-4 h-4 text-purple-700 border-gray-300 rounded focus:ring-purple-500"
            />
            <label htmlFor="online-lesson" className="ml-2 text-sm font-medium text-gray-700">
              Online
            </label>
          </div>

          {/* Address Fields */}
          <div className={`space-y-3 ${isOnlineLesson ? 'opacity-50' : ''}`}>
            <input
              type="text"
              placeholder="Street Address"
              disabled={isOnlineLesson}
              className={`w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 transition-colors ${
                isOnlineLesson ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
              }`}
              style={{ outline: 'none' }}
            />

            <div className="grid grid-cols-6 gap-3">
              <input
                type="text"
                placeholder="City"
                disabled={isOnlineLesson}
                className={`col-span-3 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 transition-colors ${
                  isOnlineLesson ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
                }`}
                style={{ outline: 'none' }}
              />

              <input
                type="text"
                placeholder="State"
                disabled={isOnlineLesson}
                className={`col-span-1 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 transition-colors ${
                  isOnlineLesson ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
                }`}
                style={{ outline: 'none' }}
              />

              <input
                type="text"
                placeholder="ZIP Code"
                disabled={isOnlineLesson}
                className={`col-span-2 w-full p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 transition-colors ${
                  isOnlineLesson ? 'bg-gray-100 cursor-not-allowed' : 'focus:border-purple-500'
                }`}
                style={{ outline: 'none' }}
              />
            </div>
          </div>
          </>
          )}
          </div>
          )}
        </div>

        {/* Action Button */}
        <div className="mt-6">
          <button
            onClick={onConfirm}
            className="w-full py-2.5 px-4 bg-purple-700 text-white hover:bg-purple-800 rounded-lg font-medium transition-colors focus:outline-none focus:ring-0"
          >
            Book now!
          </button>
        </div>

        <p className="text-xs text-center text-gray-500 dark:text-gray-400 mt-4">
          🔒 Secure payment • {!isLastMinute && 'Cancel free >24hrs'}
        </p>
      </div>

      {/* Right Column - Booking Details - 40% width */}
      <div className="w-[40%] bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700 order-1 md:order-2">
        <h3 className="font-bold text-xl mb-4">Booking Your Lesson with</h3>
        <div className="space-y-4">
          <div className="flex items-start">
            <div className="w-16 h-16 bg-gray-200 dark:bg-gray-700 rounded-full mr-4"></div>
            <div>
              <h4 className="font-semibold">{booking.instructorName}</h4>
              <div className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
                <Star className="h-4 w-4 text-yellow-500 fill-current" />
                <span className="font-medium">4.8</span>
                <span>·</span>
                <span>47 reviews</span>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-2">
              Piano Lesson
            </div>
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
            <div className="flex items-start text-sm">
              <MapPin size={16} className="mr-2 text-gray-500 mt-0.5" />
              <div>
                {isOnlineLesson ? (
                  <div>Online</div>
                ) : booking.location ? (
                  <div>{booking.location}</div>
                ) : (
                  <>
                    <div>123 Main Street, Apt 4B</div>
                    <div>New York, NY 10001</div>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Edit Lesson Button */}
          <div className="mt-4">
            <button
              onClick={() => {
                // Navigate back to instructor profile to edit the lesson
                if (booking.instructorId) {
                  window.location.href = `/instructors/${booking.instructorId}`;
                }
              }}
              className="bg-white text-purple-700 py-1.5 px-3 rounded-lg text-sm font-medium border-2 border-purple-700 hover:bg-purple-50 transition-colors"
            >
              Edit lesson
            </button>
          </div>

          {/* Message Instructor Section */}
          <div className="mt-4">
            <textarea
              placeholder="What should your instructor know about this session?"
              className="w-full p-3 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 resize-none transition-colors"
              style={{ outline: 'none', boxShadow: 'none' }}
              onFocus={(e) => e.target.style.boxShadow = 'none'}
              rows={6}
            />
          </div>

          {/* Payment Details Section */}
          <div className="border-t border-gray-300 pt-4">
            <h4 className="font-semibold mb-3">Payment details</h4>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Lesson ({booking.duration} min)</span>
                <span>${booking.basePrice.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span>Service fee</span>
                <span>${booking.serviceFee.toFixed(2)}</span>
              </div>
              {creditsUsed > 0 && (
                <div className="flex justify-between text-sm text-green-600 dark:text-green-400">
                  <span>Credits applied</span>
                  <span>-${creditsUsed.toFixed(2)}</span>
                </div>
              )}
              <div className="border-t border-gray-300 pt-2 mt-2">
                <div className="flex justify-between font-bold text-base">
                  <span>Total Rate</span>
                  <span>${booking.totalAmount.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Cancellation Policy */}
          <div className="rounded-lg p-3 text-sm" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
            <h4 className="font-medium mb-2 flex items-center">
              <AlertCircle size={16} className="mr-1" />
              Cancellation Policy
            </h4>
            <div className="space-y-0.5 text-gray-600 dark:text-gray-400" style={{ fontSize: '11px' }}>
              <p>More than 24 hours before your lesson: Full refund</p>
              <p>12–24 hours before your lesson: Refund issued as platform credit</p>
              <p>Less than 12 hours before your lesson: No refund</p>
            </div>
          </div>

        </div>
      </div>
      </div>
    </div>
  );
}
