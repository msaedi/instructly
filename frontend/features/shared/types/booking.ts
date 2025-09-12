// Canonical booking-related shared types/constants used across features

export enum BookingType {
  STANDARD = 'standard',
  LAST_MINUTE = 'last_minute',
  PACKAGE = 'package',
}

export const TRANSACTION_LIMITS = {
  MAX_TRANSACTION: 1000, // $1,000 max per transaction
  CREDIT_EXPIRY_MONTHS: 12,
  SERVICE_FEE_PERCENTAGE: 20,
};

export enum PaymentStatus {
  PENDING = 'pending',
  AUTHORIZED = 'authorized',
  CAPTURED = 'captured',
  FAILED = 'failed',
  REFUNDED = 'refunded',
  RELEASED = 'released',
}

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
  serviceFee: number;
  totalAmount: number;

  bookingType: BookingType;
  paymentStatus: PaymentStatus;
  stripeIntentId?: string;

  // Cancellation info
  freeCancellationUntil?: Date;
  creditCancellationUntil?: Date;
}
