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
export type BookingCreate = components['schemas']['BookingCreate'];
export type AvailabilityCheckRequest = components['schemas']['AvailabilityCheckRequest'];
export type AvailabilityCheckResponse = components['schemas']['AvailabilityCheckResponse'];
export type BookingPreview = components['schemas']['BookingPreviewResponse'];

// Paginated wrappers with useful aliases
export type BookingList = components['schemas']['PaginatedResponse_BookingResponse_'];
export type BookingListResponse = components['schemas']['PaginatedResponse_BookingResponse_'];
export type UpcomingBookingList = components['schemas']['PaginatedResponse_UpcomingBookingResponse_'];

// Search responses
export type InstructorSearchResponse = components['schemas']['InstructorSearchResponse'];
export type NaturalLanguageSearchResponse = components['schemas']['InstructorSearchResponse'];

// Availability types
export type TimeSlot = components['schemas']['TimeSlot'];
export type PublicTimeSlot = components['schemas']['PublicTimeSlot'];

// Review types
export type ReviewListPageResponse = components['schemas']['ReviewListPageResponse'];
export type ReviewResponseModel = components['schemas']['ReviewResponseModel'];
export type ReviewSubmitResponse = components['schemas']['ReviewSubmitResponse'];

// Additional commonly used types
export type BookingStatus = components['schemas']['BookingStatus'];
export type AddressResponse = components['schemas']['AddressResponse'];
export type ServiceInfo = components['schemas']['ServiceInfo'];
export type StudentInfo = components['schemas']['StudentInfo'];
export type InstructorInfo = components['schemas']['app__schemas__booking__InstructorInfo'];
export type FavoritedInstructor = components['schemas']['FavoritedInstructor'];
export type FavoriteResponse = components['schemas']['FavoriteResponse'];
export type FavoriteStatusResponse = components['schemas']['FavoriteStatusResponse'];
export type FavoritesListResponse = components['schemas']['FavoritesList'];
export type InstructorService = components['schemas']['InstructorServiceResponse'];
export type InstructorServiceResponse = components['schemas']['InstructorServiceResponse'];
