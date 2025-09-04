/**
 * Type shim for generated OpenAPI types
 *
 * Single import surface for generated OpenAPI types.
 * NOTE: type-only re-exports to avoid bundling.
 */

// Re-export all types from generated API under namespace
export type * as Gen from '@/types/generated/api';

// Import and re-export components for use in other files
import type { components } from '@/types/generated/api';
export type { components };

// Canonical aliases for commonly used models (import these, not from Gen.* directly)
export type User = components['schemas']['UserWithPermissionsResponse'];
export type Booking = components['schemas']['BookingResponse'];
export type InstructorProfile = components['schemas']['InstructorProfileResponse'];

// Common endpoint payloads
export type CreateBookingRequest = components['schemas']['BookingCreate'];
export type CreateBookingResponse = components['schemas']['BookingResponse'];

// Paginated wrappers with useful aliases
export type BookingList = components['schemas']['PaginatedResponse_BookingResponse_'];

// Additional commonly used types
export type BookingStatus = components['schemas']['BookingStatus'];
export type AddressResponse = components['schemas']['AddressResponse'];
export type ServiceInfo = components['schemas']['ServiceInfo'];
export type StudentInfo = components['schemas']['StudentInfo'];
export type InstructorInfo = components['schemas']['app__schemas__booking__InstructorInfo'];
