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
import { captureDeviceContext, formatDeviceContextForAnalytics } from '@/lib/deviceContext';

import { withApiBase } from '@/lib/apiBase';
import { httpGet, httpPost } from '@/lib/http';

// Build URL using centralized API base resolver
function buildUrl(path: string): string {
  return withApiBase(path);
}

export interface SearchRecord {
  query: string;
  search_type: SearchType;
  results_count?: number | null;
  timestamp?: string;
  // Optional: top-N candidates from search response for observability persistence
  observability_candidates?: Array<Record<string, unknown>>;
}

export interface SearchHistoryItem {
  id?: number;
  query: string;
  search_type: SearchType;
  results_count?: number | null;
  timestamp: string;
  created_at?: string;
}

/**
 * Ensure guest_id cookie exists by calling the session bootstrap endpoint once
 */
async function ensureGuestCookie(): Promise<void> {
  if (typeof document === 'undefined') return;
  const hasGuest = document.cookie.split('; ').some((c) => c.startsWith('guest_id='));
  if (hasGuest) return;
  try {
    await httpPost(withApiBase('/api/public/session/guest'));
    logger.info('Bootstrapped guest_id cookie');
  } catch (e) {
    logger.warn('Failed to bootstrap guest session');
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
function getHeaders(isAuthenticated: boolean): HeadersInit {
  const headers: HeadersInit = {
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
    await ensureGuestCookie();
    logger.debug('Recording search', { searchRecord, isAuthenticated });

    // Refresh session on search activity
    refreshSession();

    // Get analytics context
    const analyticsContext = getAnalyticsContext();

    // Capture device context
    const deviceContext = captureDeviceContext();
    const deviceInfo = formatDeviceContextForAnalytics(deviceContext);

    logger.debug('Search tracking - device context', { deviceContext });
    logger.debug('Search tracking - device info', { deviceInfo });

    // Build payload with optional observability candidates if provided
    const body: {
      search_query: string;
      search_type: SearchType;
      results_count?: number | null;
      search_context: { page: string; viewport: string; timestamp: string; page_view_count: number; session_duration: number };
      device_context: Record<string, unknown>;
      observability_candidates?: Array<Record<string, unknown>>;
    } = {
      search_query: searchRecord.query,
      search_type: searchRecord.search_type,
      results_count: searchRecord.results_count,
      search_context: analyticsContext,
      device_context: deviceInfo,
    };
    if (searchRecord.observability_candidates && searchRecord.observability_candidates.length > 0) {
      body.observability_candidates = searchRecord.observability_candidates;
    }

    const data = (await httpPost(buildUrl('/api/search-history/'), body)) as any;
    logger.info('Search recorded successfully', { searchRecord, responseData: data });

    // Trigger update event for UI components
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new Event(isAuthenticated ? 'searchHistoryUpdated' : 'guestSearchUpdated')
      );
    }

    // Return the search event ID for interaction tracking
    return data.search_event_id || null;
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
): Promise<SearchHistoryItem[]> {
  try {
    await ensureGuestCookie();
    const data = (await httpGet(buildUrl('/api/search-history/'), { query: { limit } })) as any[];
    return data as SearchHistoryItem[];
  } catch (error) {
    logger.error('Error fetching recent searches', error as Error);

    // Fallback to sessionStorage for guests
    if (!isAuthenticated) {
      return getGuestSearches().map(record => ({
        ...record,
        timestamp: record.timestamp || new Date().toISOString()
      })).slice(0, limit);
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
    // Ensure headers are properly set for both authenticated and guest users
    const headers = getHeaders(isAuthenticated);

    logger.debug('Tracking search interaction', {
      searchEventId,
      interactionType,
      instructorId,
      resultPosition,
      timeToInteraction,
      isAuthenticated,
    });

    await httpPost(buildUrl('/api/search-history/interaction'), {
      search_event_id: searchEventId,
      interaction_type: interactionType,
      instructor_id: instructorId,
      result_position: resultPosition,
      time_to_interaction: timeToInteraction,
    });

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
    const response = await fetch(buildUrl(`/api/search-history/${searchId}`), {
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
