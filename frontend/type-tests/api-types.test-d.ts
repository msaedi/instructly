import type { Gen } from '@/features/shared/api/types';
import type { Booking, InstructorProfile, User } from '../types';

// Basic shape checks for critical models
type _UserIdIsString = User['id'] extends string ? true : never;
type _UserEmailIsString = User['email'] extends string ? true : never;

// Booking status is the generated enum union (uppercase from API)
type _BookingStatusIsUnion = Gen.components['schemas']['BookingStatus'] extends
  | 'PENDING'
  | 'CONFIRMED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'NO_SHOW'
  ? true
  : never;

// BookingResponse.status must be that union
type _BookingResponseStatusMatches = Booking['status'] extends Gen.components['schemas']['BookingStatus']
  ? true
  : never;

// Instructor Profile must have a user_id string
type _InstructorHasUserId = InstructorProfile['user_id'] extends string ? true : never;

// Keep surface minimal to avoid unused-var churn
