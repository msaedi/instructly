// frontend/lib/searchTracking.ts
/**
 * Search tracking utilities for recording user searches
 *
 * Handles both authenticated (database) and unauthenticated (sessionStorage) tracking
 */

import { publicApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';

export interface SearchRecord {
  query: string;
  search_type: 'natural_language' | 'category' | 'service_pill' | 'filter';
  results_count?: number | null;
  timestamp?: string;
}

/**
 * Records a search for the current user (authenticated or guest)
 */
export async function recordSearch(
  searchRecord: SearchRecord,
  isAuthenticated: boolean
): Promise<void> {
  try {
    logger.debug('Recording search', { searchRecord, isAuthenticated });

    if (isAuthenticated) {
      // For authenticated users, record to database via API
      const response = await publicApi.recordSearchHistory({
        search_query: searchRecord.query,
        search_type: searchRecord.search_type,
        results_count: searchRecord.results_count,
      });

      if (response.error) {
        logger.error('Failed to record search to database', new Error(response.error), {
          searchRecord,
          response,
          token: typeof window !== 'undefined' ? localStorage.getItem('access_token') : null,
        });
      } else {
        logger.info('Search recorded to database', {
          searchRecord,
          responseData: response.data,
        });

        // Dispatch event for authenticated users too, to update UI immediately
        window.dispatchEvent(new Event('searchHistoryUpdated'));
      }
    } else {
      // For guests, store in sessionStorage
      const searches = getGuestSearches();

      // Remove duplicate if exists and add to beginning
      const filteredSearches = searches.filter((s) => s.query !== searchRecord.query);
      const newSearches = [
        { ...searchRecord, timestamp: new Date().toISOString() },
        ...filteredSearches,
      ].slice(0, 10); // Keep max 10 for guests

      sessionStorage.setItem('recentSearches', JSON.stringify(newSearches));
      logger.debug('Search recorded to sessionStorage', searchRecord);

      // Dispatch custom event for same-tab updates
      window.dispatchEvent(new Event('guestSearchUpdated'));
    }
  } catch (error) {
    // Don't throw - search tracking should never break the main functionality
    logger.error('Error recording search', error as Error);
  }
}

/**
 * Gets guest searches from sessionStorage
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
 * Clears guest searches from sessionStorage
 */
export function clearGuestSearches(): void {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('recentSearches');
  }
}

/**
 * Transfers guest searches to user account (called after login)
 */
export async function transferGuestSearchesToAccount(): Promise<void> {
  const guestSearches = getGuestSearches();

  if (guestSearches.length === 0) {
    return;
  }

  try {
    // Record each search to the user's account
    // Going in reverse order so oldest searches are recorded first
    for (const search of guestSearches.reverse()) {
      await publicApi.recordSearchHistory({
        search_query: search.query,
        search_type: search.search_type,
        results_count: search.results_count,
      });
    }

    // Clear guest searches after successful transfer
    clearGuestSearches();
    logger.info('Transferred guest searches to user account', {
      count: guestSearches.length,
    });
  } catch (error) {
    logger.error('Failed to transfer guest searches', error as Error);
  }
}
