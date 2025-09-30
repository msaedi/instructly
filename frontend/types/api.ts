// frontend/types/api.ts

import type { ServiceAreaNeighborhood } from '@/types/instructor';

/**
 * API Type Definitions
 *
 * This module contains TypeScript interfaces and types specific to
 * API communication patterns, including response wrappers, request
 * states, and standardized API structures.
 *
 * @module api
 */

/**
 * Generic API response wrapper
 *
 * Provides a consistent structure for all API responses
 *
 * @interface APIResponse
 * @template T - The type of data in the response
 */
export interface APIResponse<T> {
  /** The response data */
  data: T;

  /** Whether the request was successful */
  success: boolean;

  /** Optional message (for errors or info) */
  message?: string;

  /** Response metadata */
  meta?: ResponseMeta;

  /** Validation errors if any */
  errors?: ValidationErrorMap;

  /** Response timestamp */
  timestamp?: string;
}

/**
 * Response metadata
 *
 * @interface ResponseMeta
 */
export interface ResponseMeta {
  /** Request ID for tracking */
  request_id?: string;

  /** Response time in milliseconds */
  response_time?: number;

  /** API version */
  version?: string;

  /** Rate limit information */
  rate_limit?: RateLimitInfo;
}

/**
 * Rate limit information
 *
 * @interface RateLimitInfo
 */
export interface RateLimitInfo {
  /** Maximum requests allowed */
  limit: number;

  /** Remaining requests */
  remaining: number;

  /** Reset timestamp */
  reset_at: string;
}

/**
 * Map of validation errors by field
 */
export type ValidationErrorMap = Record<string, string[]>;

/**
 * Request status for tracking async operations
 */
export enum RequestStatus {
  /** Initial state */
  IDLE = 'idle',

  /** Request in progress */
  LOADING = 'loading',

  /** Request succeeded */
  SUCCESS = 'success',

  /** Request failed */
  ERROR = 'error',
}

/**
 * Request state for React components
 *
 * @interface RequestState
 * @template T - The type of data being requested
 */
export interface RequestState<T> {
  /** Current request status */
  status: RequestStatus;

  /** The data (if successful) */
  data: T | null;

  /** Error information (if failed) */
  error: string | null;

  /** Whether this is the first load */
  isInitialLoad: boolean;

  /** Timestamp of last successful fetch */
  lastFetchTime?: number;
}

/**
 * API configuration options
 *
 * @interface APIConfig
 */
export interface APIConfig {
  /** Base URL for API */
  baseURL: string;

  /** Default timeout in milliseconds */
  timeout?: number;

  /** Default headers */
  headers?: Record<string, string>;

  /** Whether to include credentials */
  withCredentials?: boolean;

  /** Retry configuration */
  retry?: RetryConfig;
}

/**
 * Retry configuration for failed requests
 *
 * @interface RetryConfig
 */
export interface RetryConfig {
  /** Maximum number of retries */
  maxRetries: number;

  /** Initial delay in milliseconds */
  initialDelay: number;

  /** Maximum delay in milliseconds */
  maxDelay: number;

  /** Backoff multiplier */
  backoffMultiplier: number;

  /** Which status codes to retry */
  retryableStatuses?: number[];
}

/**
 * File upload progress information
 *
 * @interface UploadProgress
 */
export interface UploadProgress {
  /** Bytes uploaded */
  loaded: number;

  /** Total bytes to upload */
  total: number;

  /** Progress percentage (0-100) */
  percentage: number;

  /** Estimated time remaining in seconds */
  estimatedTimeRemaining?: number;

  /** Upload speed in bytes per second */
  speed?: number;
}

/**
 * Batch operation request
 *
 * @interface BatchRequest
 * @template T - The type of operations
 */
export interface BatchRequest<T> {
  /** Array of operations to perform */
  operations: T[];

  /** Whether to stop on first error */
  stopOnError?: boolean;

  /** Whether to validate only (dry run) */
  validateOnly?: boolean;
}

/**
 * Batch operation response
 *
 * @interface BatchResponse
 * @template T - The type of results
 */
export interface BatchResponse<T> {
  /** Results for each operation */
  results: BatchResult<T>[];

  /** Summary statistics */
  summary: {
    total: number;
    successful: number;
    failed: number;
    skipped: number;
  };
}

/**
 * Individual batch operation result
 *
 * @interface BatchResult
 * @template T - The type of result data
 */
export interface BatchResult<T> {
  /** Operation index */
  index: number;

  /** Operation status */
  status: 'success' | 'error' | 'skipped';

  /** Result data (if successful) */
  data?: T;

  /** Error information (if failed) */
  error?: string;

  /** Additional details */
  details?: Record<string, unknown>;
}

/**
 * Webhook event payload
 *
 * @interface WebhookEvent
 */
export interface WebhookEvent {
  /** Event ID */
  id: string;

  /** Event type */
  type: string;

  /** Event timestamp */
  timestamp: string;

  /** Event data */
  data: Record<string, unknown>;

  /** Webhook signature for verification */
  signature?: string;
}

/**
 * Instructor type for search results and listings
 */
export interface Instructor {
  /** Instructor profile ID (ULID string) */
  id: string;

  /** Associated user ID (ULID string) */
  user_id: string;

  /** Brief bio/description */
  bio: string;

  /** Ordered list of borough labels derived from service areas */
  service_area_boroughs?: string[];

  /** Detailed neighborhood metadata for service areas */
  service_area_neighborhoods?: ServiceAreaNeighborhood[];

  /** Human-readable summary provided by backend */
  service_area_summary?: string | null;

  /** Years of teaching experience */
  years_experience: number;

  /** Minimum advance booking hours required */
  min_advance_booking_hours?: number;

  /** Buffer time between sessions in minutes */
  buffer_time_minutes?: number;

  /** User information */
  user: {
    /** First name */
    first_name: string;
    /** Last initial for privacy */
    last_initial: string;
  };

  /** Services offered */
  services: Array<{
    /** Service ID (ULID string) */
    id: string;
    /** Service catalog ID (ULID string) */
    service_catalog_id: string;
    /** Hourly rate */
    hourly_rate: number;
    /** Service description */
    description?: string;
    /** Duration options in minutes */
    duration_options?: number[];
    /** Whether service is active */
    is_active?: boolean;
  }>;

  /** Optional relevance score for search results */
  relevance_score?: number;

  /** Average rating */
  rating?: number;

  /** Total number of reviews */
  total_reviews?: number;

  /** Total hours taught */
  total_hours_taught?: number;

  /** Whether instructor is verified */
  verified?: boolean;

  /** Creation timestamp */
  created_at?: string;

  /** Update timestamp */
  updated_at?: string;
}

/**
 * Type guard to check if a value is a successful API response
 *
 * @param response - Response to check
 * @returns boolean indicating if response is successful
 */
export function isSuccessResponse<T>(
  response: APIResponse<T>
): response is APIResponse<T> & { data: T } {
  return response.success === true && response.data !== null && response.data !== undefined;
}

/**
 * Type guard to check if request is in loading state
 *
 * @param state - Request state to check
 * @returns boolean indicating if loading
 */
export function isLoading<T>(state: RequestState<T>): boolean {
  return state.status === RequestStatus.LOADING;
}

/**
 * Type guard to check if request has error
 *
 * @param state - Request state to check
 * @returns boolean indicating if error
 */
export function hasError<T>(state: RequestState<T>): boolean {
  return state.status === RequestStatus.ERROR && state.error !== null;
}

/**
 * Create initial request state
 *
 * @returns Initial RequestState
 */
export function createInitialRequestState<T>(): RequestState<T> {
  return {
    status: RequestStatus.IDLE,
    data: null,
    error: null,
    isInitialLoad: true,
  };
}

/**
 * Helper to handle API errors consistently
 *
 * @param error - Error from API call
 * @returns Standardized error message
 */
export function handleAPIError(error: unknown): string {
  const err = error as Record<string, unknown>;

  if (err?.['response'] && typeof err['response'] === 'object') {
    const response = err['response'] as Record<string, unknown>;
    if (response?.['data'] && typeof response['data'] === 'object') {
      const data = response['data'] as Record<string, unknown>;
      if (data?.['detail']) {
        return typeof data['detail'] === 'string'
          ? data['detail']
          : 'Validation error occurred';
      }
    }
  }

  if (err?.['message'] && typeof err['message'] === 'string') {
    return err['message'];
  }

  return 'An unexpected error occurred. Please try again.';
}

// ============================================================================
// SHARED DOMAIN TYPES
// ============================================================================

/**
 * Service offered by an instructor
 *
 * @interface Service
 */
export interface Service {
  /** Service ID (ULID string) */
  id: string;

  /** Reference to service catalog item (ULID string) */
  service_catalog_id: string;

  /** Hourly rate for this service */
  hourly_rate: number;

  /** Optional description of the service */
  description?: string;

  /** Available duration options in minutes */
  duration_options: number[];

  /** Whether the service is currently active */
  is_active?: boolean;
}

/**
 * Service catalog item (master list of available services)
 *
 * @interface ServiceCatalogItem
 */
export interface ServiceCatalogItem {
  /** Catalog item ID */
  id: string;

  /** Service name */
  name: string;

  /** Category this service belongs to */
  category_id: string;

  /** Optional description */
  description?: string;
}
