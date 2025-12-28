// Canonical booking-related shared types/constants used across features
import type { PaymentStatus } from '@/features/shared/types/paymentStatus';
export type { PaymentStatus } from '@/features/shared/types/paymentStatus';

export enum BookingType {
  STANDARD = 'standard',
  LAST_MINUTE = 'last_minute',
  PACKAGE = 'package',
}

export const TRANSACTION_LIMITS = {
  MAX_TRANSACTION: 1000, // $1,000 max per transaction
  CREDIT_EXPIRY_MONTHS: 12,
};

export interface BookingPayment {
  bookingId: string;
  instructorId: string;
  instructorName: string;
  lessonType: string;
  date: Date;
  startTime: string;
  endTime: string;
  duration: number;
  location: string;

  basePrice: number;
  totalAmount: number;

  bookingType: BookingType;
  paymentStatus: PaymentStatus;
  stripeIntentId?: string;

  // Cancellation info
  freeCancellationUntil?: Date;
  creditCancellationUntil?: Date;
}
