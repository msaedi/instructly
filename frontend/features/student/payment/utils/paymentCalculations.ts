import { differenceInHours } from 'date-fns';
import { BookingType, TRANSACTION_LIMITS } from '../types';

export const calculateServiceFee = (basePrice: number): number => {
  return basePrice * (TRANSACTION_LIMITS.SERVICE_FEE_PERCENTAGE / 100);
};

export const calculateTotalAmount = (basePrice: number): number => {
  const serviceFee = calculateServiceFee(basePrice);
  return basePrice + serviceFee;
};

export const determineBookingType = (lessonDate: Date): BookingType => {
  const hoursUntilLesson = differenceInHours(lessonDate, new Date());
  return hoursUntilLesson < 24 ? BookingType.LAST_MINUTE : BookingType.STANDARD;
};

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

export const validateTransactionAmount = (amount: number): boolean => {
  return amount > 0 && amount <= TRANSACTION_LIMITS.MAX_TRANSACTION;
};

export const formatCurrency = (amount: number): string => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
};

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
