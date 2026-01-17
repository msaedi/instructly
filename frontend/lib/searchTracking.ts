// frontend/lib/searchTracking.ts
/**
 * Unified search tracking for both authenticated and guest users.
 *
 * This module provides a single set of functions that work for both user types
 * without duplication, using headers to differentiate.
 */

import { logger } from '@/lib/logger';
import { getSessionId, refreshSession, getAnalyticsContext } from '@/lib/sessionTracking';
import { SearchType } from '@/types/enums';
import type { components } from '@/features/shared/api/types';
import { captureDeviceContext, formatDeviceContextForAnalytics } from '@/lib/deviceContext';

import { withApiBase } from '@/lib/apiBase';
import { httpGet, httpPost, postWithRetry } from '@/lib/http';
import { env } from '@/lib/env';

// Build URL using centralized API base resolver
function buildUrl(path: string): string {
  return withApiBase(path);
}

// Shared API paths (v1)
const SEARCH_HISTORY_BASE_PATH = '/api/v1/search-history';
const SEARCH_HISTORY_INTERACTION_PATH = `${SEARCH_HISTORY_BASE_PATH}/interaction`;

export interface SearchRecord {
  query: string;
  search_type: SearchType;
  results_count?: number | null;
  timestamp?: string;
  // Optional: top-N candidates from search response for observability persistence
  observability_candidates?: Array<Record<string, unknown>>;
}

type SearchHistoryCreate = components['schemas']['SearchHistoryCreate'];
export type SearchHistoryResponse = components['schemas']['SearchHistoryResponse'];
export type SearchHistoryItem = SearchHistoryResponse;
type SearchInteractionResponse = components['schemas']['SearchInteractionResponse'];

/**
 * Ensure guest_id cookie exists by calling the session bootstrap endpoint once
 * Concurrency-safe and skipped if a user session is active.
 */
let guestBootstrapInFlight = false;
let guestBootstrapDone = false;
export async function ensureGuestOnce(): Promise<void> {
  // Skip guest bootstrap during unit tests to avoid extra network calls
  if (typeof process !== 'undefined' && env.isTest()) return;
  if (typeof document === 'undefined') return;
  // Always trust the cookie first; if absent, we must bootstrap regardless of any local sentinel
  const hasGuest = document.cookie.split('; ').some((c) => c.startsWith('guest_id='));
  if (hasGuest) {
    guestBootstrapDone = true;
    try { localStorage.setItem('guest_bootstrap_done', 'true'); } catch {}
    return;
  }
  try {
    if (localStorage.getItem('guest_bootstrap_done') === 'true') {
      // Sentinel is stale (cookie missing); continue to bootstrap
      // fallthrough
    }
  } catch {}
  if (guestBootstrapDone || guestBootstrapInFlight) return;
  try {
    guestBootstrapInFlight = true;
    await postWithRetry('/api/v1/public/session/guest', { method: 'POST' });
    guestBootstrapDone = true;
    try { localStorage.setItem('guest_bootstrap_done', 'true'); } catch {}
    logger.info('Bootstrapped guest_id cookie');
  } catch {
    logger.warn('Failed to bootstrap guest session');
  } finally {
    guestBootstrapInFlight = false;
  }
}

/**
 * Clean up expired guest sessions
 */
function cleanupExpiredSessions(): boolean {
  if (typeof window === 'undefined') return false;

  const expiry = localStorage.getItem('guest_session_expiry');
  if (expiry && Date.now() > parseInt(expiry)) {
    localStorage.removeItem('guest_session_id');
    localStorage.removeItem('guest_session_expiry');
    // Also clear any associated data
    sessionStorage.removeItem('recentSearches');
    return true; // Indicates a new session is needed
  }
  return false;
}

/**
 * Get or create persistent guest session ID with 30-day expiration
 */
export function getGuestSessionId(): string {
  if (typeof window === 'undefined') return '';

  // Clean up expired sessions first
  const needsNewSession = cleanupExpiredSessions();

  const GUEST_SESSION_KEY = 'guest_session_id';
  const EXPIRY_KEY = 'guest_session_expiry';

  let sessionId = localStorage.getItem(GUEST_SESSION_KEY);
  const expiry = localStorage.getItem(EXPIRY_KEY);

  // Check if exists and not expired
  if (sessionId && expiry && Date.now() < parseInt(expiry) && !needsNewSession) {
    return sessionId;
  }

  // Create new session with 30-day expiry
  sessionId = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });

  const expiryTime = Date.now() + 30 * 24 * 60 * 60 * 1000; // 30 days

  localStorage.setItem(GUEST_SESSION_KEY, sessionId);
  localStorage.setItem(EXPIRY_KEY, expiryTime.toString());

  logger.info('Created new persistent guest session', { sessionId, expiryDays: 30 });

  return sessionId;
}

/**
 * Get headers for API requests based on authentication state
 */
function getHeaders(isAuthenticated: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // Add authorization header if authenticated
  if (isAuthenticated && typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  // Add guest session ID if not authenticated
  if (!isAuthenticated) {
    const guestSessionId = getGuestSessionId();
    if (guestSessionId) {
      headers['X-Guest-Session-ID'] = guestSessionId;
    }
  }

  // Add analytics headers for all users
  if (typeof window !== 'undefined') {
    // Browser session ID for journey tracking
    const sessionId = getSessionId();
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }

    // Use the actual referrer or stored navigation source
    let searchOrigin = window.location.pathname; // fallback

    // Check if we have navigation tracking info
    const navigationFrom = sessionStorage.getItem('navigationFrom');
    if (navigationFrom) {
      searchOrigin = navigationFrom;
      // Clear it after use to prevent stale data
      sessionStorage.removeItem('navigationFrom');
    } else if (document.referrer) {
      // Use document.referrer if available
      try {
        const referrerUrl = new URL(document.referrer);
        searchOrigin = referrerUrl.pathname;
      } catch {
        // If parsing fails, keep the fallback
      }
    }

    headers['X-Search-Origin'] = searchOrigin;
  }

  return headers;
}

/**
 * Record a search (unified for both authenticated and guest users)
 */
export async function recordSearch(
  searchRecord: SearchRecord,
  isAuthenticated: boolean
): Promise<number | null> {
  try {
    if (!isAuthenticated) {
      await ensureGuestOnce();
    }
    logger.debug('Recording search', { searchRecord, isAuthenticated });

    // Refresh session on search activity
    refreshSession();

    // Get analytics context and map to API SearchContext type
    const rawAnalyticsContext = getAnalyticsContext();
    const [viewportWidth, viewportHeight] = rawAnalyticsContext.viewport.split('x').map(Number);
    const searchContext: SearchHistoryCreate['search_context'] = {
      page_origin: rawAnalyticsContext.page,
      viewport_width: viewportWidth || null,
      viewport_height: viewportHeight || null,
      referrer: typeof document !== 'undefined' ? document.referrer || null : null,
      session_search_count: rawAnalyticsContext.page_view_count,
    };

    // Capture device context
    const deviceContext = captureDeviceContext();
    const deviceInfo = formatDeviceContextForAnalytics(deviceContext);

    logger.debug('Search tracking - device context', { deviceContext });
    logger.debug('Search tracking - device info', { deviceInfo });

    // Build payload with optional observability candidates if provided
    const body: SearchHistoryCreate = {
      search_query: searchRecord.query,
      search_type: searchRecord.search_type,
      ...(searchRecord.results_count !== undefined && { results_count: searchRecord.results_count }),
      search_context: searchContext,
      device_context: deviceInfo,
    };
    if (searchRecord.observability_candidates && searchRecord.observability_candidates.length > 0) {
      body.observability_candidates = searchRecord.observability_candidates;
    }

    const data = await httpPost<SearchHistoryResponse>(buildUrl(SEARCH_HISTORY_BASE_PATH), body, {
      headers: getHeaders(isAuthenticated),
    });
    logger.info('Search recorded successfully', { searchRecord, responseData: data });

    // Trigger update event for UI components
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new Event(isAuthenticated ? 'searchHistoryUpdated' : 'guestSearchUpdated')
      );
    }

    // Return the search event ID for interaction tracking
    return data.search_event_id ? Number(data.search_event_id) : null;
  } catch (error) {
    logger.error('Error recording search', error as Error);

    // Fallback to sessionStorage for guests if API fails
    if (!isAuthenticated) {
      recordGuestSearchFallback(searchRecord);
    }
    return null;
  }
}

/**
 * Get recent searches (unified for both authenticated and guest users)
 */
export async function getRecentSearches(
  isAuthenticated: boolean,
  limit: number = 3
): Promise<SearchHistoryResponse[]> {
  try {
    // Ensure guest identity exists if unauthenticated (backup in case bootstrap races)
    if (!isAuthenticated) {
      const hasGuest = typeof document !== 'undefined' && document.cookie.split('; ').some((c) => c.startsWith('guest_id='));
      if (!hasGuest) {
        await ensureGuestOnce();
      }
    }
    const data = await httpGet<SearchHistoryResponse[]>(buildUrl(SEARCH_HISTORY_BASE_PATH), {
      headers: getHeaders(isAuthenticated),
      query: { limit },
    });
    return data;
  } catch (error) {
    logger.error('Error fetching recent searches', error as Error);

    // Fallback to sessionStorage for guests
    if (!isAuthenticated) {
      return getGuestSearches()
        .map((record, idx) => ({
          id: String(idx),
          search_query: record.query,
          search_type: record.search_type,
          results_count: record.results_count ?? null,
          first_searched_at: record.timestamp || new Date().toISOString(),
          last_searched_at: record.timestamp || new Date().toISOString(),
          search_count: 1,
        }))
        .slice(0, limit);
    }
    return [];
  }
}

/**
 * Track search result interaction
 */
export async function trackSearchInteraction(
  searchEventId: number,
  interactionType: 'click' | 'hover' | 'bookmark' | 'view_profile' | 'contact' | 'book',
  instructorId: string,
  resultPosition: number,
  isAuthenticated: boolean,
  timeToInteraction: number | null = null
): Promise<void> {
  try {
    logger.debug('Tracking search interaction', {
      searchEventId,
      interactionType,
      instructorId,
      resultPosition,
      timeToInteraction,
      isAuthenticated,
    });

    await httpPost<SearchInteractionResponse>(
      buildUrl(SEARCH_HISTORY_INTERACTION_PATH),
      {
        search_event_id: searchEventId,
        interaction_type: interactionType,
        instructor_id: instructorId,
        result_position: resultPosition,
        time_to_interaction: timeToInteraction,
      },
      { headers: getHeaders(isAuthenticated) }
    );

    logger.info('Search interaction tracked successfully');
  } catch (error) {
    logger.error('Error tracking search interaction', error as Error);
  }
}

/**
 * Delete a search (unified for both authenticated and guest users)
 */
export async function deleteSearch(searchId: string, isAuthenticated: boolean): Promise<boolean> {
  try {
    const response = await fetch(buildUrl(`${SEARCH_HISTORY_BASE_PATH}/${searchId}`), {
      method: 'DELETE',
      headers: getHeaders(isAuthenticated),
    });

    if (!response.ok) {
      logger.error('Failed to delete search', new Error(`Status: ${response.status}`));
      return false;
    }

    logger.info('Search deleted successfully', { searchId });

    // Trigger update event for UI components
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new Event(isAuthenticated ? 'searchHistoryUpdated' : 'guestSearchUpdated')
      );
    }

    return true;
  } catch (error) {
    logger.error('Error deleting search', error as Error);
    return false;
  }
}

/**
 * Get user preference for clearing data on logout
 */
function getUserPreference(key: string, defaultValue: boolean = false): boolean {
  if (typeof window === 'undefined') return defaultValue;

  try {
    const stored = localStorage.getItem(`user_pref_${key}`);
    return stored ? JSON.parse(stored) : defaultValue;
  } catch {
    return defaultValue;
  }
}

/**
 * Set user preference for clearing data on logout
 */
export function setUserPreference(key: string, value: boolean): void {
  if (typeof window !== 'undefined') {
    localStorage.setItem(`user_pref_${key}`, JSON.stringify(value));
  }
}

/**
 * Clear guest session on logout (respects user preference)
 */
export function clearGuestSession(forceLogout: boolean = false): void {
  if (typeof window === 'undefined') return;

  // Check user preference (default: keep session for continuity)
  const clearDataOnLogout = forceLogout || getUserPreference('clearDataOnLogout', false);

  if (clearDataOnLogout) {
    // Clear persistent guest session data
    localStorage.removeItem('guest_session_id');
    localStorage.removeItem('guest_session_expiry');
    sessionStorage.removeItem('recentSearches');
    logger.info('Cleared guest session data on logout (user preference)');
  } else {
    // Only clear temporary session storage, keep persistent session
    sessionStorage.removeItem('recentSearches');
    logger.info('Preserved guest session on logout (default behavior)');
  }
}

/**
 * Get guest searches from session storage (fallback for offline)
 */
export function getGuestSearches(): SearchRecord[] {
  if (typeof window === 'undefined') return [];

  try {
    const stored = sessionStorage.getItem('recentSearches');
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
}

/**
 * Clear guest searches from sessionStorage
 */
export function clearGuestSearches(): void {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('recentSearches');
  }
}

/**
 * Fallback: Record guest search in sessionStorage
 */
function recordGuestSearchFallback(searchRecord: SearchRecord): void {
  const searches = getGuestSearches();
  const filteredSearches = searches.filter((s) => s.query !== searchRecord.query);
  const newSearches = [
    { ...searchRecord, timestamp: new Date().toISOString() },
    ...filteredSearches,
  ].slice(0, 10);
  sessionStorage.setItem('recentSearches', JSON.stringify(newSearches));

  // Trigger update event
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('guestSearchUpdated'));
  }
}

/**
 * Transfer guest searches to user account (handled by backend on login)
 * This is now automatic via the guest_session_id conversion
 */
export async function transferGuestSearchesToAccount(): Promise<void> {
  // The backend now handles this automatically when a user logs in
  // with a guest_session_id. We just need to clear the local storage.
  clearGuestSearches();
  logger.info('Cleared local guest searches after login');
}
