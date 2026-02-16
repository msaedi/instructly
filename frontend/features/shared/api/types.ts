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
export type { operations } from '@/types/generated/api';

// Canonical aliases for commonly used models (import these, not from Gen.* directly)
export type User = components['schemas']['AuthUserWithPermissionsResponse'];
export type Booking = components['schemas']['BookingResponse'];
export type InstructorProfile = components['schemas']['InstructorProfileResponse'];
export type InstructorProfileResponse = components['schemas']['InstructorProfileResponse'];

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
export type InstructorSearchResponse = components['schemas']['NLSearchResponse'];
export type NaturalLanguageSearchResponse = components['schemas']['NLSearchResponse'];

// Availability types
export type TimeSlot = components['schemas']['TimeSlot'];
export type PublicTimeSlot = components['schemas']['PublicTimeSlot'];
export type PublicInstructorAvailability = components['schemas']['PublicInstructorAvailability'];

// Review types
export type ReviewListPageResponse = components['schemas']['ReviewListPageResponse'];
export type ReviewResponseModel = components['schemas']['ReviewResponseModel'];
export type ReviewSubmitResponse = components['schemas']['ReviewSubmitResponse'];
export type InstructorRatingsResponse = components['schemas']['InstructorRatingsResponse'];
export type SearchRatingResponse = components['schemas']['SearchRatingResponse'];
export type RatingsBatchResponse = components['schemas']['RatingsBatchResponse'];

// Favorites
export type FavoritedInstructor = components['schemas']['FavoritedInstructor'];
export type FavoriteResponse = components['schemas']['FavoriteResponse'];
export type FavoriteStatusResponse = components['schemas']['FavoriteStatusResponse'];
export type FavoritesListResponse = components['schemas']['FavoritesList'];

// Catalog types
export type ServiceCategory = components['schemas']['CategoryResponse'];
export type CatalogService = components['schemas']['CatalogServiceResponse'];
export type CatalogServiceMinimal = components['schemas']['CatalogServiceMinimalResponse'];

// 3-level taxonomy types (Category → Subcategory → Service)
export type CategoryTreeNode = components['schemas']['CategoryTreeResponse'];
export type SubcategoryWithServices = components['schemas']['SubcategoryWithServices'];
export type SubcategoryBrief = components['schemas']['SubcategoryBrief'];
export type CategoryWithSubcategories = components['schemas']['CategoryWithSubcategories'];

// Slug-based catalog browse types (Phase 4 endpoints)
export type CategorySummary = components['schemas']['CategorySummary'];
export type CategoryDetail = components['schemas']['CategoryDetail'];
export type SubcategorySummary = components['schemas']['SubcategorySummary'];
export type SubcategoryDetail = components['schemas']['SubcategoryDetail'];
export type ServiceCatalogSummary = components['schemas']['ServiceCatalogSummary'];
export type ServiceCatalogDetail = components['schemas']['ServiceCatalogDetail'];

// Filter types
export type FilterOptionResponse = components['schemas']['FilterOptionResponse'];
export type SubcategoryFilterResponse = components['schemas']['SubcategoryFilterResponse'];
export type InstructorFilterContext = components['schemas']['InstructorFilterContext'];
export type FilterValidationResponse = components['schemas']['FilterValidationResponse'];
export type UpdateFilterSelectionsRequest = components['schemas']['UpdateFilterSelectionsRequest'];
export type ValidateFiltersRequest = components['schemas']['ValidateFiltersRequest'];

// Age group type
export type AgeGroup = 'toddler' | 'kids' | 'teens' | 'adults';

// Booking enums
export type BookingStatus = components['schemas']['BookingStatus'];

// Payment breakdown
export type PaymentSummary = components['schemas']['PaymentSummary'];

// Instructor service
export type InstructorService = components['schemas']['InstructorServiceResponse'];
export type InstructorServicesResponse = {
  services: InstructorService[];
  total: number;
};

// Referral program
export type ReferralLedgerResponse = components['schemas']['ReferralLedgerResponse'];
export type ReferralClaimResponse = components['schemas']['ReferralClaimResponse'];
export type ReferralResolveResponse = components['schemas']['ReferralResolveResponse'];
export type ReferralCheckoutApplyResponse = components['schemas']['CheckoutApplyResponse'];
export type ReferralErrorResponse = components['schemas']['ReferralErrorResponse'];
export type ReferralSendResponse = components['schemas']['ReferralSendResponse'];

// Availability types (from src/types/api.ts migration)
export type AvailabilityWindowResponse = components['schemas']['AvailabilityWindowResponse'];
export type BlackoutDateResponse = components['schemas']['BlackoutDateResponse'];
export type CopyWeekRequest = components['schemas']['CopyWeekRequest'];
export type ApplyToDateRangeRequest = components['schemas']['ApplyToDateRangeRequest'];
export type ApplyToDateRangeResponse = components['schemas']['ApplyToDateRangeResponse'] & {
  message?: string;
  weeks_applied?: number;
  weeks_affected?: number;
  days_written?: number;
  windows_created?: number;
  edited_dates?: string[];
  written_dates?: string[];
  skipped_past_targets?: number;
  start_date?: string;
  end_date?: string;
};
export type BulkUpdateRequest =
  components['schemas']['AvailabilityWindowBulkUpdateRequest'];
export type BulkUpdateResponse = components['schemas']['BulkUpdateResponse'];
export type WeekValidationResponse = components['schemas']['WeekValidationResponse'];
export type ValidateWeekRequest = components['schemas']['ValidateWeekRequest'];

// Booking stats
export type BookingStatsResponse = components['schemas']['BookingStatsResponse'];

// Password reset
export type PasswordResetRequest = components['schemas']['PasswordResetRequest'];
export type PasswordResetResponse = components['schemas']['PasswordResetResponse'];
export type PasswordResetVerifyResponse = components['schemas']['PasswordResetVerifyResponse'] & {
  valid: boolean;
  email?: string;
  error?: string;
};

// Service types
export type ServiceResponse = components['schemas']['ServiceResponse'];

// Auth types — register no longer returns user data; /me returns AuthUserWithPermissionsResponse
export type AuthUserResponse = components['schemas']['AuthUserWithPermissionsResponse'];

// Common error shape used by API endpoints
export type ApiErrorResponse = {
  detail?: string;
  message?: string;
};

// SSE token exchange - now generated from OpenAPI
export type SseTokenResponse = components['schemas']['SseTokenResponse'];

// Payment processing shim (endpoint not in OpenAPI yet)
export type PaymentProcessResponse = {
  paymentIntentId: string;
};

// Service search response includes pagination fields not currently in OpenAPI
export type ServiceSearchResponseWithPaging = components['schemas']['ServiceSearchResponse'] & {
  hasMore?: boolean;
  nextPage?: number | null;
};

// Pricing preview response (allow null instructor_tier_pct while backend normalizes)
export type PricingPreviewResponse = Omit<
  components['schemas']['PricingPreviewOut'],
  'instructor_tier_pct'
> & {
  instructor_tier_pct: number | null;
};

// Admin auth-blocks (not yet represented in OpenAPI)
export type AuthBlocksLockoutState = {
  active: boolean;
  ttl_seconds: number;
  level: string;
};
export type AuthBlocksRateLimitState = {
  active: boolean;
  count: number;
  limit: number;
  ttl_seconds: number;
};
export type AuthBlocksCaptchaState = {
  active: boolean;
};
export type AuthBlocksState = {
  lockout: AuthBlocksLockoutState | null;
  rate_limit_minute: AuthBlocksRateLimitState | null;
  rate_limit_hour: AuthBlocksRateLimitState | null;
  captcha_required: AuthBlocksCaptchaState | null;
};
export type AuthBlockedAccount = {
  email: string;
  blocks: AuthBlocksState;
  failure_count: number;
};
export type AuthBlocksSummaryStats = {
  total_blocked: number;
  locked_out: number;
  rate_limited: number;
  captcha_required: number;
};
export type AuthBlocksListResponse = {
  accounts: AuthBlockedAccount[];
  total: number;
  scanned_at: string;
};
export type AuthBlocksClearResponse = {
  email: string;
  cleared: string[];
  cleared_by: string;
  cleared_at: string;
  reason: string | null;
};

// Admin location-learning (not yet represented in OpenAPI)
export type LocationLearningClickCount = {
  region_boundary_id: string;
  region_name?: string | null;
  count: number;
};
export type LocationLearningUnresolvedQuery = {
  id: string;
  query_normalized: string;
  search_count: number;
  unique_user_count: number;
  click_count: number;
  clicks: LocationLearningClickCount[];
  sample_original_queries: string[];
  first_seen_at: string;
  last_seen_at: string;
  status: string;
};
export type LocationLearningUnresolvedQueriesResponse = {
  queries: LocationLearningUnresolvedQuery[];
  total: number;
};
export type LocationLearningPendingAlias = {
  id: string;
  alias_normalized: string;
  region_boundary_id?: string | null;
  region_name?: string | null;
  confidence: number;
  user_count: number;
  status: string;
  created_at: string;
};
export type LocationLearningPendingAliasesResponse = {
  aliases: LocationLearningPendingAlias[];
};
export type LocationLearningRegionOption = {
  id: string;
  name: string;
  borough?: string | null;
};
export type LocationLearningRegionsResponse = {
  regions: LocationLearningRegionOption[];
};

// Admin referrals (not yet represented in OpenAPI)
export type AdminReferralsHealth = {
  workers_alive: number;
  workers: string[];
  backlog_pending_due: number;
  pending_total: number;
  unlocked_total: number;
  void_total: number;
  last_run_age_s: number | null;
};
export type AdminReferralsSummary = {
  counts_by_status: Record<string, number>;
  cap_utilization_percent: number;
  top_referrers: { user_id: string; count: number; code: string | null }[];
  clicks_24h: number;
  attributions_24h: number;
};

// Availability update error payload (version conflict)
export type AvailabilityUpdateErrorResponse = ApiErrorResponse & {
  error?: string;
  current_version?: string;
};

// Service areas and neighborhoods
export type ServiceAreaItem = components['schemas']['ServiceAreaItem'];
export type ServiceAreasResponse = components['schemas']['ServiceAreasResponse'];
export type NeighborhoodsListResponse = components['schemas']['NeighborhoodsListResponse'];
export type NYCZipCheckResponse = components['schemas']['NYCZipCheckResponse'];
export type AddressResponse = components['schemas']['AddressResponse'];
export type AddressListResponse = components['schemas']['AddressListResponse'];

// Top services per category (homepage)
export type TopCategoryItem = components['schemas']['TopCategoryItem'];
export type TopCategoryServiceItem = components['schemas']['TopCategoryServiceItem'];
export type TopServicesPerCategoryResponse = components['schemas']['TopServicesPerCategoryResponse'];
export type CategoryServiceDetail = components['schemas']['CategoryServiceDetail'];
export type CategoryWithServices = components['schemas']['CategoryWithServices'];
export type AllServicesWithInstructorsResponse = components['schemas']['AllServicesWithInstructorsResponse'];

// Badges and awards
export type BadgeProgressView = components['schemas']['BadgeProgressView'];
export type StudentBadgeView = components['schemas']['StudentBadgeView'];
export type AdminAwardBadgeSchema = components['schemas']['AdminAwardBadgeSchema'];
export type AdminAwardStudentSchema = components['schemas']['AdminAwardStudentSchema'];
export type AdminAwardSchema = components['schemas']['AdminAwardSchema'];
export type AdminAwardListResponse = components['schemas']['AdminAwardListResponse'];

// Search history
export type SearchHistoryResponse = components['schemas']['SearchHistoryResponse'];

// Analytics types (admin dashboard)
export type SearchTrendsResponse = components['schemas']['SearchTrendsResponse'];
export type PopularSearchesResponse = components['schemas']['PopularSearchesResponse'];
export type SearchReferrersResponse = components['schemas']['SearchReferrersResponse'];
export type CandidateCategoryTrendsResponse = components['schemas']['CandidateCategoryTrendsResponse'];
export type CandidateTopServicesResponse = components['schemas']['CandidateTopServicesResponse'];
export type CandidateServiceQueriesResponse = components['schemas']['CandidateServiceQueriesResponse'];
export type CandidateScoreDistributionResponse = components['schemas']['CandidateScoreDistributionResponse'];
export type CodebaseMetricsResponse = components['schemas']['CodebaseMetricsResponse'];
export type CodebaseHistoryResponse = components['schemas']['CodebaseHistoryResponse'];
export type CodebaseCategoryStats = components['schemas']['CodebaseCategoryStats'];
export type CodebaseSection = components['schemas']['CodebaseSection'];
export type CodebaseHistoryEntry = components['schemas']['CodebaseHistoryEntry'];
export type DailySearchTrend = components['schemas']['DailySearchTrend'];
export type PopularSearch = components['schemas']['PopularSearch'];
export type SearchReferrer = components['schemas']['SearchReferrer'];
export type ZeroResultQueryItem = components['schemas']['ZeroResultQueryItem'];
export type SearchAnalyticsSummaryResponse = components['schemas']['SearchAnalyticsSummaryResponse'];
export type ConversionMetricsResponse = components['schemas']['ConversionMetricsResponse'];
export type SearchPerformanceResponse = components['schemas']['SearchPerformanceResponse'];
export type CandidateSummaryResponse = components['schemas']['CandidateSummaryResponse'];
export type CandidateCategoryTrend = components['schemas']['CandidateCategoryTrend'];
export type CandidateTopService = components['schemas']['CandidateTopService'];
export type CandidateServiceQuery = components['schemas']['CandidateServiceQuery'];

// Redis monitoring types (admin dashboard)
export type RedisHealthResponse = components['schemas']['RedisHealthResponse'];
export type RedisStatsResponse = components['schemas']['RedisStatsResponse'];
export type RedisCeleryQueuesResponse = components['schemas']['RedisCeleryQueuesResponse'];
export type RedisConnectionAuditResponse = components['schemas']['RedisConnectionAuditResponse'];
export type RedisTestResponse = components['schemas']['RedisTestResponse'];

// Database monitoring types (admin dashboard)
export type DatabaseHealthResponse = components['schemas']['DatabaseHealthResponse'];
export type DatabaseStatsResponse = components['schemas']['DatabaseStatsResponse'];
export type DatabasePoolStatusResponse = components['schemas']['DatabasePoolStatusResponse'];

// Upload types
export type SignedUploadResponse = components['schemas']['SignedUploadResponse'];
export type ProxyUploadResponse = components['schemas']['ProxyUploadResponse'];
export type CreateSignedUploadRequest = components['schemas']['CreateSignedUploadRequest'];

// Common response types
export type SuccessResponse = components['schemas']['SuccessResponse'];
export type IdentitySessionResponse = components['schemas']['IdentitySessionResponse'];
export type OnboardingStatusResponse = components['schemas']['OnboardingStatusResponse'];

// Auth types
export type LoginResponse = components['schemas']['LoginResponse'];

// Beta types
export type BetaSettingsResponse = components['schemas']['BetaSettingsResponse'];
export type BetaSettingsUpdateRequest = components['schemas']['BetaSettingsUpdateRequest'];
export type PerformanceMetricsResponse = components['schemas']['PerformanceMetricsResponse'];
export type BetaMetricsSummaryResponse = components['schemas']['BetaMetricsSummaryResponse'];

// Pricing types
export type PricingConfigResponse = components['schemas']['PricingConfigResponse'];
export type PricingLineItem = components['schemas']['LineItem'];
export type PricingTierConfig = components['schemas']['TierConfig'];
export type PricingConfig = components['schemas']['PricingConfig'];
export type PricingPreviewQuotePayload = components['schemas']['PricingPreviewIn'];

// Conversation types
export type ConversationListResponse = components['schemas']['ConversationListResponse'];
export type CreateConversationResponse = components['schemas']['CreateConversationResponse'];
export type ConversationDetail = components['schemas']['ConversationDetail'];
export type ConversationListItem = components['schemas']['ConversationListItem'];

// Finalize profile picture payload
export type FinalizeProfilePicturePayload = components['schemas']['FinalizeProfilePicturePayload'];

// Upcoming booking response
export type UpcomingBookingResponse = components['schemas']['UpcomingBookingResponse'];

// Availability update types
export type WeekAvailabilityResponse = components['schemas']['WeekAvailabilityResponse'];
export type WeekAvailabilityUpdateResponse = components['schemas']['WeekAvailabilityUpdateResponse'];
export type CopyWeekResponse = components['schemas']['CopyWeekResponse'];

// Payment types
export type PaymentMethodResponse = components['schemas']['PaymentMethodResponse'];
export type PaymentMethod = components['schemas']['PaymentMethodResponse']; // Alias for backwards compat
export type SavePaymentMethodRequest = components['schemas']['SavePaymentMethodRequest'];
export type CreateCheckoutRequest = components['schemas']['CreateCheckoutRequest'];
export type EarningsResponse = components['schemas']['EarningsResponse'];
export type InstructorInvoice = components['schemas']['InstructorInvoiceSummary']; // Generated uses Summary suffix
export type InstructorInvoiceSummary = components['schemas']['InstructorInvoiceSummary'];
export type PayoutSummary = components['schemas']['PayoutSummary'];
export type PayoutHistoryResponse = components['schemas']['PayoutHistoryResponse'];
export type OnboardingResponse = components['schemas']['OnboardingResponse'];
export type Transaction = components['schemas']['TransactionHistoryItem']; // Alias for backwards compat
export type TransactionHistoryItem = components['schemas']['TransactionHistoryItem'];

// Instructor referral types
export type ReferralStatsResponse = components['schemas']['ReferralStatsResponse'];
export type ReferredInstructorInfo = components['schemas']['ReferredInstructorInfo'];
export type ReferredInstructorsResponse = components['schemas']['ReferredInstructorsResponse'];
export type FoundingStatusResponse = components['schemas']['FoundingStatusResponse'];
export type PopupDataResponse = components['schemas']['PopupDataResponse'];

// Additional booking types
export type BookingCreateResponse = components['schemas']['BookingCreateResponse'];
export type BookedSlotsResponse = components['schemas']['BookedSlotsResponse'];

// Admin booking types
export type AdminBookingListResponse = components['schemas']['AdminBookingListResponse'];
export type AdminBookingStatsResponse = components['schemas']['AdminBookingStatsResponse'];

// Admin audit types
export type AuditLogListResponse = components['schemas']['AuditLogListResponse'];
export type AdminAuditEntry = components['schemas']['AdminAuditEntry'];

// Paginated instructor list
export type InstructorListResponse = components['schemas']['PaginatedResponse_InstructorProfileResponse_'];
export type PaginatedInstructorProfileResponse = components['schemas']['PaginatedResponse_InstructorProfileResponse_'];
