// Payment types following A-Team's hybrid model

export enum PaymentStatus {
  PENDING = 'pending',
  AUTHORIZED = 'authorized',
  CAPTURED = 'captured',
  LOCKED = 'locked',
  FAILED = 'failed',
  REFUNDED = 'refunded',
  RELEASED = 'released',
}

export enum PaymentMethod {
  CREDIT_CARD = 'credit_card',
  DEBIT_CARD = 'debit_card',
  CREDITS = 'credits',
  MIXED = 'mixed', // Credits + Card
}

export { BookingType } from '@/features/shared/types/booking';

export interface PaymentIntent {
  id: string;
  amount: number;
  currency: string;
  status: PaymentStatus;
  captureMethod: 'manual' | 'automatic';
  metadata: Record<string, unknown>;
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
  totalAmount: number;

  bookingType: import('@/features/shared/types/booking').BookingType;
  paymentStatus: PaymentStatus;
  stripeIntentId?: string;

  // For mixed payments
  creditsAvailable?: number;
  creditsApplied?: number;
  cardAmount?: number;

  // Cancellation info
  freeCancellationUntil?: Date;
  creditCancellationUntil?: Date;
}

export interface CreditBalance {
  totalAmount: number;
  credits: Credit[];
  // Optional: earliest expiration across available credits (ISO string)
  earliestExpiry?: string | null;
}

export interface Credit {
  id: string;
  amount: number;
  source: string;
  expiresAt: Date;
  createdAt: Date;
  instructorId?: string; // If credit is instructor-specific
}

export interface PaymentCard {
  id: string;
  last4: string;
  brand: string;
  expiryMonth: number;
  expiryYear: number;
  isDefault: boolean;
}

export interface TipOption {
  percentage: number;
  amount: number;
}

export const DEFAULT_TIP_OPTIONS: TipOption[] = [
  { percentage: 0, amount: 0 },
  { percentage: 15, amount: 0 },
  { percentage: 20, amount: 0 },
  { percentage: 25, amount: 0 },
];

export { TRANSACTION_LIMITS } from '@/features/shared/types/booking';
