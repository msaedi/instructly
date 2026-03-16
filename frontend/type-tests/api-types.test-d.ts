import type { Gen } from '@/features/shared/api/types';
import type { Booking, InstructorProfile, User } from '../types';

// Basic shape checks for critical models
export type UserIdIsString = User['id'] extends string ? true : never;
export type UserEmailIsString = User['email'] extends string ? true : never;

// Booking status is the generated enum union (uppercase from API)
export type BookingStatusIsUnion = Gen.components['schemas']['BookingStatus'] extends
  | 'PENDING'
  | 'CONFIRMED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'NO_SHOW'
  ? true
  : never;

// BookingResponse.status must be that union
export type BookingResponseStatusMatches = Booking['status'] extends Gen.components['schemas']['BookingStatus']
  ? true
  : never;

// Instructor Profile must have a user_id string
export type InstructorHasUserId = InstructorProfile['user_id'] extends string ? true : never;

// Keep surface minimal to avoid unused-var churn
