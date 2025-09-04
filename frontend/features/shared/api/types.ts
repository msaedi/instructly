/**
 * Type shim for generated OpenAPI types
 *
 * This file re-exports types from the auto-generated API definitions
 * and provides convenient aliases for commonly used schemas.
 */

// Re-export all types from generated API
export type * from '@/types/generated/api';

// Import for creating aliases
import type { components } from '@/types/generated/api';

// Convenient aliases for frequently used schemas
export type User = components['schemas']['UserWithPermissionsResponse'];
export type Booking = components['schemas']['BookingResponse'];
export type InstructorProfile = components['schemas']['InstructorProfileResponse'];
export type PaginatedBookings = components['schemas']['PaginatedResponse_BookingResponse_'];

// Additional commonly used types
export type BookingStatus = components['schemas']['BookingStatus'];
export type AddressResponse = components['schemas']['AddressResponse'];
export type ServiceInfo = components['schemas']['ServiceInfo'];
export type StudentInfo = components['schemas']['StudentInfo'];
export type InstructorInfo = components['schemas']['app__schemas__booking__InstructorInfo'];
