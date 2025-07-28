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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface SearchRecord {
  query: string;
  search_type: SearchType;
  results_count?: number | null;
  timestamp?: string;
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

    // Current page path for referrer analytics
    headers['X-Search-Origin'] = window.location.pathname;
  }

  return headers;
}

/**
 * Record a search (unified for both authenticated and guest users)
 */
export async function recordSearch(
  searchRecord: SearchRecord,
  isAuthenticated: boolean
): Promise<void> {
  try {
    logger.debug('Recording search', { searchRecord, isAuthenticated });

    // Refresh session on search activity
    refreshSession();

    // Get analytics context
    const analyticsContext = getAnalyticsContext();

    const response = await fetch(`${API_BASE_URL}/api/search-history/`, {
      method: 'POST',
      headers: getHeaders(isAuthenticated),
      body: JSON.stringify({
        search_query: searchRecord.query,
        search_type: searchRecord.search_type,
        results_count: searchRecord.results_count,
        search_context: analyticsContext,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error(
        'Failed to record search',
        new Error(`Status: ${response.status}, ${errorText}`)
      );

      // Fallback to sessionStorage for guests if API fails
      if (!isAuthenticated) {
        recordGuestSearchFallback(searchRecord);
      }
      return;
    }

    const data = await response.json();
    logger.info('Search recorded successfully', { searchRecord, responseData: data });

    // Trigger update event for UI components
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new Event(isAuthenticated ? 'searchHistoryUpdated' : 'guestSearchUpdated')
      );
    }
  } catch (error) {
    logger.error('Error recording search', error as Error);

    // Fallback to sessionStorage for guests if API fails
    if (!isAuthenticated) {
      recordGuestSearchFallback(searchRecord);
    }
  }
}

/**
 * Get recent searches (unified for both authenticated and guest users)
 */
export async function getRecentSearches(
  isAuthenticated: boolean,
  limit: number = 3
): Promise<any[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/search-history/?limit=${limit}`, {
      method: 'GET',
      headers: getHeaders(isAuthenticated),
    });

    if (!response.ok) {
      logger.error('Failed to fetch recent searches', new Error(`Status: ${response.status}`));

      // Fallback to sessionStorage for guests
      if (!isAuthenticated) {
        return getGuestSearches().slice(0, limit);
      }
      return [];
    }

    const data = await response.json();
    return data;
  } catch (error) {
    logger.error('Error fetching recent searches', error as Error);

    // Fallback to sessionStorage for guests
    if (!isAuthenticated) {
      return getGuestSearches().slice(0, limit);
    }
    return [];
  }
}

/**
 * Delete a search (unified for both authenticated and guest users)
 */
export async function deleteSearch(searchId: number, isAuthenticated: boolean): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/search-history/${searchId}`, {
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
