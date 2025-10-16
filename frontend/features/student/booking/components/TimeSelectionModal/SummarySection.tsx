'use client';

import { useMemo } from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { Info } from 'lucide-react';
import {
  formatCentsToDisplay,
  type PricingPreviewResponse,
} from '@/lib/api/pricing';
import { usePricingConfig } from '@/lib/pricing/usePricingFloors';
import {
  computeStudentFeePercent,
  formatServiceSupportLabel,
  formatServiceSupportTooltip,
} from '@/lib/pricing/studentFee';

interface SummarySectionProps {
  selectedDate: string | null;
  selectedTime: string | null;
  selectedDuration: number;
  price: number;
  onContinue: () => void;
  isComplete: boolean;
  floorWarning?: string | null;
  pricingPreview?: PricingPreviewResponse | null;
  isPricingPreviewLoading?: boolean;
  pricingError?: string | null;
  hasBookingDraft?: boolean;
}

export default function SummarySection({
  selectedDate,
  selectedTime,
  selectedDuration,
  price,
  onContinue,
  isComplete,
  floorWarning = null,
  pricingPreview = null,
  isPricingPreviewLoading = false,
  pricingError = null,
  hasBookingDraft = false,
}: SummarySectionProps) {
  const { config: pricingConfig } = usePricingConfig();
  const serviceSupportFeePercent = useMemo(
    () => computeStudentFeePercent({ preview: pricingPreview, config: pricingConfig }),
    [pricingConfig, pricingPreview],
  );
  const serviceSupportVisibleLabel = useMemo(
    () => formatServiceSupportLabel(serviceSupportFeePercent, { includeFeeWord: false }),
    [serviceSupportFeePercent],
  );
  const serviceSupportAriaLabel = useMemo(
    () => formatServiceSupportLabel(serviceSupportFeePercent),
    [serviceSupportFeePercent],
  );
  const serviceSupportTooltip = useMemo(
    () => formatServiceSupportTooltip(serviceSupportFeePercent),
    [serviceSupportFeePercent],
  );
  // Format date to human-readable format
  const formatDate = (dateStr: string, timeStr: string) => {
    // Parse the date string as local date, not UTC
    // Split the date string and create date with local timezone
    const dateParts = dateStr.split('-');
    const year = parseInt(dateParts[0] || '0', 10);
    const month = parseInt(dateParts[1] || '0', 10);
    const day = parseInt(dateParts[2] || '0', 10);
    const date = new Date(year, month - 1, day); // month is 0-indexed

    const monthNames = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    const monthName = monthNames[date.getMonth()];
    const dayNum = date.getDate();

    // Convert time to 12-hour format if needed
    const formattedTime =
      timeStr.includes('am') || timeStr.includes('pm') ? timeStr : formatTime24to12(timeStr);

    return `${monthName} ${dayNum}, ${formattedTime}`;
  };

  // Convert 24-hour time to 12-hour format
  const formatTime24to12 = (time24: string) => {
    const timeParts = time24.split(':');
    const hours = parseInt(timeParts[0] || '0', 10);
    const minutes = parseInt(timeParts[1] || '0', 10);
    const period = hours >= 12 ? 'pm' : 'am';
    const hour12 = hours % 12 || 12;
    return `${hour12}:${minutes.toString().padStart(2, '0')}${period}`;
  };

  // Don't show anything if no selections made
  if (!selectedDate && !selectedTime) {
    return null;
  }

  return (
    <div className="w-full">
      <div className="text-center">
        {/* Request for header */}
        <p className="text-sm mb-1" style={{ color: '#666666' }}>
          Request for:
        </p>

        {/* Date and Time */}
        {selectedDate && selectedTime && (
          <p className="text-lg font-bold mb-1" style={{ color: '#333333', fontSize: '18px' }}>
            {formatDate(selectedDate, selectedTime)}
          </p>
        )}

        {/* Duration and Pricing */}
        {selectedDuration && (
          <div className="mb-4">
            <p className="text-base" style={{ color: '#333333', fontSize: '16px' }}>
              {selectedDuration} min
              {!pricingPreview && price > 0 ? ` · $${price}` : ''}
            </p>

            {pricingPreview && (
              <div className="mt-3 rounded-lg border border-gray-200 bg-white p-3 text-sm text-left space-y-2">
                <div className="flex justify-between">
                  <span>Lesson</span>
                  <span>{formatCentsToDisplay(pricingPreview.base_price_cents)}</span>
                </div>
                {pricingPreview.line_items.map((item) => {
                  const isCredit = item.amount_cents < 0;
                  const normalizedLabel = (() => {
                    const label = item.label.toLowerCase();
                    if (label.startsWith('booking protection') || label.startsWith('service & support')) {
                      return serviceSupportAriaLabel;
                    }
                    return item.label;
                  })();
                  const isServiceSupportLineItem = normalizedLabel === serviceSupportAriaLabel;
                  return (
                    <div
                      key={`${item.label}-${item.amount_cents}`}
                      className={`flex justify-between text-gray-700 ${
                        isCredit ? 'text-green-600 dark:text-green-400' : ''
                      }`}
                    >
                      {isServiceSupportLineItem ? (
                        <span className="inline-flex items-center gap-1" aria-label={serviceSupportAriaLabel}>
                          <span>{serviceSupportAriaLabel}</span>
                          <Tooltip.Provider delayDuration={150} skipDelayDuration={75}>
                            <Tooltip.Root>
                              <Tooltip.Trigger asChild>
                                <button
                                  type="button"
                                  className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
                                  aria-label="Learn about the Service & Support fee"
                                >
                                  <Info className="h-3.5 w-3.5" aria-hidden="true" />
                                </button>
                              </Tooltip.Trigger>
                          <Tooltip.Content
                            side="top"
                            sideOffset={6}
                            className="max-w-xs whitespace-pre-line rounded-md bg-gray-900 px-2 py-1 text-xs text-white shadow text-left"
                          >
                            {serviceSupportTooltip}
                            <Tooltip.Arrow className="fill-gray-900" />
                          </Tooltip.Content>
                            </Tooltip.Root>
                          </Tooltip.Provider>
                        </span>
                      ) : (
                        <span>{normalizedLabel}</span>
                      )}
                      <span>{formatCentsToDisplay(item.amount_cents)}</span>
                    </div>
                  );
                })}
                <div className="flex justify-between font-semibold text-base border-t border-gray-200 pt-2">
                  <span>Total</span>
                  <span>{formatCentsToDisplay(pricingPreview.student_pay_cents)}</span>
                </div>
              </div>
            )}

            {isPricingPreviewLoading && hasBookingDraft && (
              <p className="mt-2 text-xs text-gray-500">Updating pricing…</p>
            )}

            {pricingError && (
              <p className="mt-2 text-xs text-red-600">{pricingError}</p>
            )}

            {!hasBookingDraft && (
              <p className="mt-2 text-xs text-gray-500">
                <span className="inline-flex items-center gap-1" aria-label={serviceSupportAriaLabel}>
                  <span>{serviceSupportVisibleLabel}</span>
                  <Tooltip.Provider delayDuration={150} skipDelayDuration={75}>
                    <Tooltip.Root>
                      <Tooltip.Trigger asChild>
                        <button
                          type="button"
                          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 transition-colors hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
                          aria-label="Learn about the Service & Support fee"
                        >
                          <Info className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </Tooltip.Trigger>
                  <Tooltip.Content
                    side="top"
                    sideOffset={6}
                    className="max-w-xs whitespace-pre-line rounded-md bg-gray-900 px-2 py-1 text-xs text-white shadow text-left"
                  >
                    {serviceSupportTooltip}
                    <Tooltip.Arrow className="fill-gray-900" />
                  </Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </span>{' '}
                and credits apply at checkout.
              </p>
            )}
          </div>
        )}

        {/* Continue Button */}
        <button
          onClick={onContinue}
          disabled={!isComplete}
          className={`
            w-full py-2.5 px-4 rounded-lg font-medium transition-colors
            ${
              isComplete
                ? 'bg-[#7E22CE] text-white hover:bg-[#7E22CE]'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }
          `}
        >
          Select and continue
        </button>

        {floorWarning && (
          <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {floorWarning}
          </div>
        )}

        {/* Helper Text */}
        <p
          className="mt-4 text-sm leading-relaxed px-2"
          style={{
            color: '#666666',
            fontSize: '13px',
            lineHeight: '1.4',
          }}
        >
          Next, confirm your details and start learning
        </p>
      </div>
    </div>
  );
}
