import { differenceInHours } from 'date-fns';
import { BookingType } from '@/features/shared/types/booking';

export const determineBookingType = (lessonDate: Date): BookingType => {
  const hoursUntilLesson = differenceInHours(lessonDate, new Date());
  return hoursUntilLesson < 24 ? BookingType.LAST_MINUTE : BookingType.STANDARD;
};
