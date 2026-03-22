import { TRANSACTION_LIMITS } from '@/features/shared/types/booking';
import { formatPrice } from '@/lib/price';

export const calculateCreditApplication = (
  totalAmount: number,
  availableCredits: number,
  maxCreditsAllowed?: number
): { creditsToUse: number; remainingAmount: number } => {
  const maxCredits = maxCreditsAllowed || totalAmount;
  const creditsToUse = Math.min(availableCredits, maxCredits, totalAmount);
  const remainingAmount = totalAmount - creditsToUse;

  return {
    creditsToUse,
    remainingAmount,
  };
};

export { determineBookingType } from '@/features/shared/utils/paymentCalculations';
export type { BookingType } from '@/features/shared/types/booking';

export const validateTransactionAmount = (amount: number): boolean => amount > 0 && amount <= TRANSACTION_LIMITS.MAX_TRANSACTION;

export const formatCurrency = (amount: number): string => formatPrice(amount);

export const calculateTipAmount = (baseAmount: number, tipPercentage: number): number => {
  return baseAmount * (tipPercentage / 100);
};

export const getTimezoneOffset = (): string => {
  const date = new Date();
  const offset = -date.getTimezoneOffset();
  const hours = Math.floor(Math.abs(offset) / 60);
  const minutes = Math.abs(offset) % 60;
  const sign = offset >= 0 ? '+' : '-';

  return `${sign}${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
};
