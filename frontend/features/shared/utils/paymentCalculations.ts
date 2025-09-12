import { differenceInHours } from 'date-fns';
import { BookingType, TRANSACTION_LIMITS } from '@/features/shared/types/booking';

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
