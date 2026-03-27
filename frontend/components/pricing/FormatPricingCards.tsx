'use client';

import { ToggleSwitch } from '@/components/ui/ToggleSwitch';
import {
  FORMAT_CARD_CONFIGS,
  MAX_HOURLY_RATE,
  type FormatPriceState,
  type ServiceFormat,
  getHourlyRateValidationMessage,
} from '@/lib/pricing/formatPricing';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';

type FormatPricingCardsProps = {
  formatPrices: FormatPriceState;
  onChange: (next: FormatPriceState) => void;
  priceFloors: PriceFloorConfig | null;
  durationOptions: number[];
  takeHomePct: number;
  platformFeeLabel: string;
  formatErrors?: Partial<Record<ServiceFormat, string>> | undefined;
  studentLocationDisabled?: boolean | undefined;
  studentLocationDisabledReason?: string | undefined;
};

export function FormatPricingCards({
  formatPrices,
  onChange,
  takeHomePct,
  platformFeeLabel,
  formatErrors,
  studentLocationDisabled,
  studentLocationDisabledReason,
}: FormatPricingCardsProps) {
  function isEnabled(format: ServiceFormat): boolean {
    return format in formatPrices;
  }

  function isCardDisabled(format: ServiceFormat): boolean {
    if (format === 'student_location') return studentLocationDisabled === true;
    return false;
  }

  function getDisabledReason(format: ServiceFormat): string | undefined {
    if (format === 'student_location') return studentLocationDisabledReason;
    return undefined;
  }

  function handleToggle(format: ServiceFormat) {
    if (isEnabled(format)) {
      // Turn OFF — remove key from state
      const next: FormatPriceState = {};
      for (const config of FORMAT_CARD_CONFIGS) {
        if (config.format !== format && config.format in formatPrices) {
          next[config.format] = formatPrices[config.format]!;
        }
      }
      onChange(next);
    } else {
      // Turn ON — add key with empty string
      const next: FormatPriceState = { ...formatPrices };
      next[format] = '';
      onChange(next);
    }
  }

  function handleRateChange(format: ServiceFormat, value: string) {
    const next: FormatPriceState = { ...formatPrices };
    next[format] = value;
    onChange(next);
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {FORMAT_CARD_CONFIGS.map((config) => {
        const enabled = isEnabled(config.format);
        const disabled = isCardDisabled(config.format);
        const disabledReason = getDisabledReason(config.format);
        const rate = formatPrices[config.format] ?? '';
        const rateNum = Number(rate);
        const showTakeHome = rate !== '' && rateNum > 0;
        const validationError = getHourlyRateValidationMessage(rate);
        const error = validationError ?? formatErrors?.[config.format];

        return (
          <div
            key={config.format}
            data-testid={`format-card-${config.format}`}
            className={`rounded-lg border border-gray-200 dark:border-gray-700 p-4 transition-opacity duration-200 ${
              enabled && !disabled ? 'opacity-100 bg-white dark:bg-gray-800' : 'opacity-40 bg-gray-50 dark:bg-gray-900'
            }`}
          >
            {/* Header: label + toggle */}
            <div className="flex items-start justify-between gap-2 mb-3">
              <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                {config.label}
              </h4>
              <ToggleSwitch
                checked={enabled && !disabled}
                onChange={() => handleToggle(config.format)}
                disabled={disabled}
                ariaLabel={config.label}
              />
            </div>

            {/* Rate input */}
            <div className="mb-3">
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 block mb-1">
                Hourly Rate
              </label>
              <div className="flex items-center gap-1">
                <span className="text-gray-500 dark:text-gray-400">$</span>
                <input
                  type="number"
                  min={0}
                  max={MAX_HOURLY_RATE}
                  step="1"
                  inputMode="decimal"
                  placeholder={config.placeholderRate}
                  value={rate}
                  disabled={!enabled || disabled}
                  aria-invalid={error ? 'true' : 'false'}
                  onChange={(e) => handleRateChange(config.format, e.target.value)}
                  className={`w-20 rounded-md border px-2 py-1.5 text-center font-medium focus:outline-none focus:ring-2 focus:ring-(--color-brand-dark)/20 focus:border-purple-500 ${
                    error
                      ? 'border-red-500'
                      : 'border-gray-300 dark:border-gray-600'
                  } disabled:bg-gray-100 dark:disabled:bg-gray-800 disabled:cursor-not-allowed`}
                />
                <span className="text-sm text-gray-500 dark:text-gray-400">/hr</span>
              </div>

              {/* Take-home display */}
              {showTakeHome && (
                <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                  You&apos;ll earn{' '}
                  <span className="font-semibold text-(--color-brand-dark)">
                    ${(rateNum * takeHomePct).toFixed(2)}
                  </span>{' '}
                  after the {platformFeeLabel} platform fee
                </p>
              )}

              {/* Inline error */}
              {error && (
                <p className="mt-1 text-xs text-red-600">{error}</p>
              )}
            </div>

            {/* Description */}
            <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
              {config.description}
            </p>

            {/* Disabled reason */}
            {disabled && disabledReason && (
              <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                {disabledReason}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
