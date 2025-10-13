'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Calendar, Clock, MapPin, AlertCircle, Star, ChevronDown } from 'lucide-react';
import { BookingPayment, PaymentMethod } from '../types';
import { BookingType } from '@/features/shared/types/booking';
import { format } from 'date-fns';
import { protectedApi } from '@/features/shared/api/client';
import { httpJson } from '@/features/shared/api/http';
import { withApiBase } from '@/lib/apiBase';
import { loadInstructorProfileSchema } from '@/features/shared/api/schemas/instructorProfile';
import type { InstructorService } from '@/types/instructor';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import { calculateEndTime } from '@/features/student/booking/hooks/useCreateBooking';
import { determineBookingType } from '@/features/shared/utils/paymentCalculations';
import { logger } from '@/lib/logger';
import { usePricingFloors } from '@/lib/pricing/usePricingFloors';
import {
  computeBasePriceCents,
  computePriceFloorCents,
  formatCents,
  type NormalizedModality,
} from '@/lib/pricing/priceFloors';

interface PaymentConfirmationProps {
  booking: BookingPayment;
  paymentMethod: PaymentMethod;
  cardLast4?: string;
  creditsUsed?: number;
  availableCredits?: number;
  creditEarliestExpiry?: string | Date | null;
  onConfirm: () => void;
  onBack: () => void;
  onChangePaymentMethod?: () => void;
  onCreditToggle?: () => void;
  onCreditAmountChange?: (amount: number) => void;
  cardBrand?: string;
  isDefaultCard?: boolean;
  promoApplied?: boolean;
  onPromoStatusChange?: (applied: boolean) => void;
  referralAppliedCents?: number;
  referralActive?: boolean;
  floorViolationMessage?: string | null;
  onClearFloorViolation?: () => void;
}

export default function PaymentConfirmation({
  booking,
  paymentMethod,
  cardLast4,
  creditsUsed = 0,
  availableCredits = 0,
  creditEarliestExpiry = null,
  onConfirm,
  onBack: _onBack, // Kept for interface compatibility but not used
  onChangePaymentMethod,
  onCreditToggle,
  onCreditAmountChange,
  cardBrand = 'Card',
  isDefaultCard = false,
  promoApplied = false,
  onPromoStatusChange,
  referralAppliedCents = 0,
  referralActive: referralActiveFromParent = false,
  floorViolationMessage = null,
  onClearFloorViolation,
}: PaymentConfirmationProps) {
  const [isOnlineLesson, setIsOnlineLesson] = useState(false);
  const [hasConflict, setHasConflict] = useState(false);
  const [conflictMessage, setConflictMessage] = useState<string>('');
  const [isCheckingConflict, setIsCheckingConflict] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [instructorServices, setInstructorServices] = useState<InstructorService[]>([]);
  const [loadingInstructor, setLoadingInstructor] = useState(false);
  const [promoCode, setPromoCode] = useState('');
  const [promoActive, setPromoActive] = useState(promoApplied);
  const [promoError, setPromoError] = useState<string | null>(null);
  const { floors: pricingFloors } = usePricingFloors();

  // Track if credits are enabled (slider is shown) separately from amount
  const creditsEnabled = paymentMethod === PaymentMethod.MIXED || paymentMethod === PaymentMethod.CREDITS;

  logger.info('PaymentConfirmation component rendered', {
    booking,
    hasConflict,
    isCheckingConflict
  });
  // Auto-collapse payment if user has a saved card
  const hasSavedCard = !!cardLast4;
  const [isPaymentExpanded, setIsPaymentExpanded] = useState(!hasSavedCard);
  // Auto-collapse location if they have a saved address or it's online
  const hasSavedLocation = booking.location && booking.location !== '';
  const [isLocationExpanded, setIsLocationExpanded] = useState(!hasSavedLocation && !isOnlineLesson);
  const isLastMinute = booking.bookingType === BookingType.LAST_MINUTE;
  const referralCreditAmount = referralAppliedCents / 100;
  const referralActive = referralActiveFromParent || referralCreditAmount > 0;
  const cardCharge = Math.max(0, booking.totalAmount - creditsUsed - referralCreditAmount);
  const totalAfterCredits = Math.max(0, booking.totalAmount - creditsUsed - referralCreditAmount);
  const promoApplyDisabled = referralActive || (!promoActive && promoCode.trim().length === 0);

  const selectedModality = useMemo<NormalizedModality>(() => (isOnlineLesson ? 'remote' : 'in_person'), [isOnlineLesson]);
  const hourlyRate = useMemo(() => {
    if (!Number.isFinite(booking.duration) || booking.duration <= 0) return 0;
    return Number(((booking.basePrice || 0) * 60) / booking.duration);
  }, [booking.basePrice, booking.duration]);

  const clientFloorViolation = useMemo(() => {
    if (!pricingFloors) return null;
    if (!Number.isFinite(hourlyRate) || hourlyRate <= 0) return null;
    if (!Number.isFinite(booking.duration) || booking.duration <= 0) return null;
    const floorCents = computePriceFloorCents(pricingFloors, selectedModality, booking.duration);
    const baseCents = computeBasePriceCents(hourlyRate, booking.duration);
    if (baseCents < floorCents) {
      return { floorCents, baseCents };
    }
    return null;
  }, [pricingFloors, hourlyRate, booking.duration, selectedModality]);

  const clientFloorWarning = useMemo(() => {
    if (!clientFloorViolation) return null;
    const modalityLabel = selectedModality === 'in_person' ? 'in-person' : 'remote';
    return `Minimum for ${modalityLabel} ${booking.duration}-minute private session is $${formatCents(clientFloorViolation.floorCents)} (current $${formatCents(clientFloorViolation.baseCents)}).`;
  }, [clientFloorViolation, booking.duration, selectedModality]);

  const activeFloorMessage = clientFloorWarning ?? floorViolationMessage ?? null;
  const isFloorBlocking = Boolean(activeFloorMessage);

  useEffect(() => {
    setPromoActive(promoApplied);
    if (!promoApplied) {
      setPromoError(null);
    }
  }, [promoApplied]);

  useEffect(() => {
    const modalityFromMetadata = (booking as unknown as { metadata?: Record<string, unknown> }).metadata?.['modality'];
    if (modalityFromMetadata === 'remote') {
      setIsOnlineLesson(true);
      return;
    }
    if (modalityFromMetadata === 'in_person') {
      setIsOnlineLesson(false);
      return;
    }
    if (typeof booking.location === 'string' && booking.location) {
      setIsOnlineLesson(/online|remote/i.test(booking.location));
    }
  }, [booking]);

  useEffect(() => {
    if (!referralActive) {
      return;
    }
    if (promoActive) {
      setPromoActive(false);
      onPromoStatusChange?.(false);
    }
    if (promoCode) {
      setPromoCode('');
    }
    if (promoError) {
      setPromoError(null);
    }
  }, [referralActive, promoActive, promoCode, promoError, onPromoStatusChange]);

  // Check for booking conflicts when component mounts
  useEffect(() => {
    const checkForConflicts = async () => {
      try {
        setIsCheckingConflict(true);
        logger.info('Checking for booking conflicts...', {
          bookingDate: booking.date,
          bookingTime: `${booking.startTime}-${booking.endTime}`
        });

        // Get the student's existing bookings
        const response = await protectedApi.getBookings({ upcoming: true });
        logger.info('Fetched existing bookings', { response });
        if (response.data) {
          // Backend returns PaginatedResponse with items array
          const existingBookings = response.data.items || [];

          // Check if any existing booking conflicts with the new one
          const conflict = existingBookings.find((existing: { booking_date: string; start_time: string; end_time: string; status: string }) => {
            // Same date
            const bookingDateStr = typeof booking.date === 'string' ? booking.date : format(booking.date, 'yyyy-MM-dd');
            if (existing.booking_date !== bookingDateStr) return false;

            // Check time overlap
            const existingStart = existing.start_time;
            const existingEnd = existing.end_time;
            const newStart = booking.startTime;
            const newEnd = booking.endTime;

            // Check for overlap
            return (newStart < existingEnd && newEnd > existingStart);
          });

          if (conflict) {
            setHasConflict(true);
            setConflictMessage('You already have a booking scheduled at this time.');
            logger.warn('Booking conflict detected', {
              existingBooking: conflict,
              newBooking: booking
            });
          } else {
            logger.info('No booking conflicts found', {
              existingBookings: existingBookings.length,
              newBookingTime: `${booking.date} ${booking.startTime}-${booking.endTime}`
            });
          }
        }
      } catch (error) {
        logger.error('Failed to check for booking conflicts', error as Error);
        // Don't block booking if we can't check conflicts
      } finally {
        setIsCheckingConflict(false);
      }
    };

    void checkForConflicts();
  }, [booking]); // Re-run when booking changes

  const handlePromoAction = () => {
    if (referralActive) {
      setPromoError('Referral credit can’t be combined with a promo code.');
      return;
    }
    if (promoActive) {
      setPromoActive(false);
      setPromoError(null);
      setPromoCode('');
      onPromoStatusChange?.(false);
      return;
    }

    if (!promoCode.trim()) {
      setPromoError('Enter a promo code to apply.');
      return;
    }

    if (referralActive) {
      setPromoError('Referral credit can’t be combined with a promo code.');
      return;
    }

    setPromoActive(true);
    setPromoError(null);
    onPromoStatusChange?.(true);
  };

  const handlePromoInputChange = (value: string) => {
    setPromoCode(value);
    if (promoError) {
      setPromoError(null);
    }
  };

  // Fetch instructor profile to get the actual service duration options
  useEffect(() => {
    const fetchInstructorProfile = async () => {
      if (!booking.instructorId) return;

      setLoadingInstructor(true);
      try {
        const data = await httpJson<Record<string, unknown>>(
          withApiBase(`/instructors/${booking.instructorId}`),
          { method: 'GET' },
          loadInstructorProfileSchema,
          { endpoint: 'GET /instructors/:id' }
        );
        const services = (data as { services?: unknown[] }).services || [];
        if (services.length) {
          setInstructorServices(services.map((service: unknown) => ({
            ...(typeof service === 'object' && service !== null ? service : {}),
            description: (service as Record<string, unknown>)?.['description'] ?? null
          } as InstructorService)));
          logger.debug('Fetched instructor services', {
            services,
            instructorId: booking.instructorId
          });
        }
      } catch (error) {
        logger.error('Failed to fetch instructor profile', error);
      } finally {
        setLoadingInstructor(false);
      }
    };

    void fetchInstructorProfile();
  }, [booking.instructorId]);


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
            <div className="flex items-center gap-3 flex-1">
              <h4 className="font-bold text-xl">Payment Method</h4>
              {!isPaymentExpanded && hasSavedCard && (
                <span className="text-sm text-gray-600">•••• {cardLast4}</span>
              )}
            </div>
            <ChevronDown
              className={`h-5 w-5 text-gray-500 transition-transform ${
                isPaymentExpanded ? 'rotate-180' : ''
              }`}
            />
          </div>

          {/* Credit Card Fields */}
          {isPaymentExpanded && (
          <div className="space-y-3 mt-3">
            {hasSavedCard ? (
              <div className="bg-white p-3 rounded-lg border border-gray-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{cardBrand} ending in {cardLast4}</span>
                    {isDefaultCard && (
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">Default</span>
                    )}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (onChangePaymentMethod) {
                        onChangePaymentMethod();
                      }
                    }}
                    className="text-sm text-[#7E22CE] hover:text-[#7E22CE]"
                  >
                    Change
                  </button>
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
                className="w-4 h-4 text-[#7E22CE] border-gray-300 rounded focus:ring-[#7E22CE]"
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
              {referralActive ? (
                <div className="flex items-start gap-2 rounded-lg border border-[#7E22CE]/20 bg-[#7E22CE]/5 px-3 py-2 text-sm text-[#4f1790]">
                  <AlertCircle className="mt-0.5 h-4 w-4" aria-hidden="true" />
                  <p>Referral credit applied — promotions can’t be combined.</p>
                </div>
              ) : (
                <>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Enter promo code"
                      value={promoCode}
                      onChange={(event) => handlePromoInputChange(event.target.value)}
                      disabled={promoActive}
                      className="flex-1 p-2.5 border border-gray-200 rounded-lg text-sm placeholder-gray-400 focus:border-purple-500 transition-colors disabled:bg-gray-100"
                      style={{ outline: 'none' }}
                    />
                    <button
                      type="button"
                      onClick={handlePromoAction}
                      className="px-4 py-2.5 bg-[#7E22CE] text-white rounded-lg text-sm font-medium hover:bg-[#7E22CE] transition-colors disabled:cursor-not-allowed disabled:opacity-70"
                      disabled={promoApplyDisabled}
                    >
                      {promoActive ? 'Remove' : 'Apply'}
                    </button>
                  </div>
                  {promoError && (
                    <p className="mt-2 text-xs text-red-600">{promoError}</p>
                  )}
                  {promoActive && (
                    <p className="mt-2 text-xs text-gray-500">
                      Promo applied. Referral credit is disabled while a promo code is active.
                    </p>
                  )}
                </>
              )}
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

        {/* Available Credits Section - with interactive toggle and slider */}
        {availableCredits > 0 && (
          <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
            <div
              className="flex items-center justify-between cursor-pointer"
              onClick={() => onCreditToggle?.()}
            >
              <div className="flex-1">
                <h4 className="font-bold text-xl">Available Credits</h4>
                <p className="text-sm text-gray-600">
                  Balance: ${availableCredits.toFixed(2)}
                </p>
              </div>
              <ChevronDown
                className={`h-5 w-5 text-gray-500 transition-transform ${
                  creditsEnabled ? 'rotate-180' : ''
                }`}
              />
            </div>

            {creditsEnabled && (
              <div className="mt-3 p-3 bg-white rounded-lg">
                <div className="flex items-center justify-between text-sm mb-2">
                  <span>Credits to apply:</span>
                  <span className="font-medium">${creditsUsed.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max={Math.min(availableCredits, booking.totalAmount)}
                  step="1"
                  value={creditsUsed}
                  onChange={(e) => {
                    const newValue = Number(e.target.value);
                    onCreditAmountChange?.(newValue);
                  }}
                  className="w-full accent-purple-700"
                />
                <p className="text-xs text-gray-500 mt-2">
                  {creditsUsed >= booking.totalAmount
                    ? 'Entire lesson covered by credits!'
                    : `Remaining balance: $${(booking.totalAmount - creditsUsed).toFixed(2)}`}
                </p>
              </div>
            )}

            <p className="text-xs text-gray-500 mt-2">
              {creditEarliestExpiry
                ? `Earliest credit expiry: ${new Date(creditEarliestExpiry).toLocaleDateString()}`
                : 'Credits expire 12 months after issue date'}
            </p>
          </div>
        )}

        {/* Lesson Location */}
        <div className="mb-6 rounded-lg p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
          <div
            className="flex items-center justify-between cursor-pointer"
            onClick={() => setIsLocationExpanded(!isLocationExpanded)}
          >
            <div className="flex items-center gap-3 flex-1">
              <h4 className="font-bold text-xl">Lesson Location</h4>
              {!isLocationExpanded && (
                <span className="text-sm text-gray-600">
                  {isOnlineLesson ? 'Online' : hasSavedLocation ? booking.location : ''}
                </span>
              )}
            </div>
            <ChevronDown
              className={`h-5 w-5 text-gray-500 transition-transform ${
                isLocationExpanded ? 'rotate-180' : ''
              }`}
            />
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
                <button className="text-sm text-[#7E22CE] hover:text-[#7E22CE]">Change</button>
              </div>
            </div>
          ) : (
            <>
          <div className="flex items-center mb-4">
            <input
              type="checkbox"
              id="online-lesson"
              checked={isOnlineLesson}
              onChange={(e) => {
                setIsOnlineLesson(e.target.checked);
                onClearFloorViolation?.();
              }}
              className="w-4 h-4 text-[#7E22CE] border-gray-300 rounded focus:ring-[#7E22CE]"
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

        {activeFloorMessage && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-red-700">
                <p>{activeFloorMessage}</p>
                <p className="mt-1">Adjust the lesson duration or choose a different modality to continue.</p>
              </div>
            </div>
          </div>
        )}

        {/* Conflict Warning */}
        {hasConflict && !isCheckingConflict && (
          <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-amber-800">
                <p className="font-medium">Scheduling Conflict</p>
                <p>{conflictMessage}</p>
                <p className="mt-1">Please select a different time slot to continue.</p>
              </div>
            </div>
          </div>
        )}

        {/* Action Button */}
        <div className="mt-6">
          <button
            onClick={onConfirm}
            disabled={hasConflict || isCheckingConflict || isFloorBlocking}
            className={`w-full py-2.5 px-4 rounded-lg font-medium transition-colors focus:outline-none focus:ring-0 ${
              hasConflict || isCheckingConflict || isFloorBlocking
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-[#7E22CE] text-white hover:bg-[#7E22CE]'
            }`}
          >
            {isCheckingConflict
              ? 'Checking availability...'
              : hasConflict
              ? 'You have a conflict at this time'
              : isFloorBlocking
              ? 'Price must meet minimum'
              : 'Book now!'}
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
                // Open the calendar modal to reschedule
                setIsModalOpen(true);
              }}
              className="bg-white text-[#7E22CE] py-1.5 px-3 rounded-lg text-sm font-medium border-2 border-[#7E22CE] hover:bg-purple-50 transition-colors"
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
            {/* TODO(pricing-v1): render server Booking Protection & Credit line items. */}
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Lesson ({booking.duration} min)</span>
                <span>${booking.basePrice.toFixed(2)}</span>
              </div>
              {booking.serviceFee > 0 && (
                <div className="flex justify-between text-sm">
                  <span>Service fee</span>
                  <span>${booking.serviceFee.toFixed(2)}</span>
                </div>
              )}
              {creditsUsed > 0 && (
                <div className="flex justify-between text-sm text-green-600 dark:text-green-400">
                  <span>Credits applied</span>
                  <span>-${creditsUsed.toFixed(2)}</span>
                </div>
              )}
              {referralCreditAmount > 0 && (
                <div className="flex justify-between text-sm text-green-600 dark:text-green-400">
                  <span>Referral credit</span>
                  <span>- ${referralCreditAmount.toFixed(2)}</span>
                </div>
              )}
              <div className="border-t border-gray-300 pt-2 mt-2">
                <div className="flex justify-between font-bold text-base">
                  <span>Total Rate</span>
                  <span>${totalAfterCredits.toFixed(2)}</span>
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

      {/* Time Selection Modal */}
      {isModalOpen && !loadingInstructor && (
        <TimeSelectionModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          instructor={{
            user_id: booking.instructorId,
            user: {
              first_name: booking.instructorName.split(' ')[0] || 'Instructor',
              last_initial: booking.instructorName.split(' ')[1]?.charAt(0) || ''
            },
            services: instructorServices.length > 0
              ? instructorServices.map((service) => ({
                  id: service.id,
                  skill: service.skill || '',
                  hourly_rate: service.hourly_rate,
                  duration_options: service.duration_options || [30, 60, 90],
                  ...(Array.isArray(service.location_types)
                    ? { location_types: service.location_types }
                    : {}),
                }))
              : [{
                  id: sessionStorage.getItem('serviceId') || '',
                  skill: booking.lessonType,
                  hourly_rate: booking.basePrice / (booking.duration / 60),
                  duration_options: [30, 60, 90], // fallback to standard durations
                  location_types: ['online'],
                }]
          }}
          // Don't pre-select date/time when editing - let modal default to first available
          {...(sessionStorage.getItem('serviceId') && { serviceId: sessionStorage.getItem('serviceId')! })}
          onTimeSelected={(selection) => {
            // Update booking data with new selection
            const newBookingDate = new Date(selection.date + 'T' + selection.time);
            const hourlyRate = booking.duration > 0 ? booking.basePrice / (booking.duration / 60) : 0;
            const basePrice = Number(((hourlyRate || 0) * selection.duration) / 60);
            // TODO(pricing-v1): replace base-only fallback with server-calculated totals.
            const serviceFee = 0;
            const totalAmount = basePrice;
            const bookingType = determineBookingType(newBookingDate);

            const updatedBookingData: BookingPayment = {
              ...booking,
              date: newBookingDate,
              startTime: selection.time,
              endTime: calculateEndTime(selection.time, selection.duration),
              duration: selection.duration,
              basePrice,
              serviceFee,
              totalAmount,
              bookingType,
              ...(bookingType === BookingType.STANDARD && {
                freeCancellationUntil: new Date(newBookingDate.getTime() - 24 * 60 * 60 * 1000)
              }),
            };

            // Store updated booking data
            sessionStorage.setItem('bookingData', JSON.stringify(updatedBookingData));

            // Close modal and refresh the page with new data
            setIsModalOpen(false);
            onClearFloorViolation?.();
            window.location.reload();
          }}
        />
      )}
    </div>
  );
}
