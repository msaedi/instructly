// frontend/components/RecentSearches.tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Search, X, TrendingUp, Clock } from 'lucide-react';
import { publicApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { getGuestSearches, recordSearch, type SearchRecord } from '@/lib/searchTracking';

interface SearchHistoryItem {
  id: number;
  search_query: string;
  search_type: string;
  results_count: number | null;
  created_at: string;
}

type DisplaySearchItem = SearchHistoryItem | (SearchRecord & { id: string });

export function RecentSearches() {
  const [searches, setSearches] = useState<DisplaySearchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      fetchRecentSearches();
    } else {
      loadGuestSearches();
    }
  }, [isAuthenticated]);

  // Listen for storage changes for guest searches
  useEffect(() => {
    if (!isAuthenticated) {
      const handleStorageChange = () => {
        loadGuestSearches();
      };

      window.addEventListener('storage', handleStorageChange);

      // Also listen for custom event for same-tab updates
      window.addEventListener('guestSearchUpdated', handleStorageChange);

      return () => {
        window.removeEventListener('storage', handleStorageChange);
        window.removeEventListener('guestSearchUpdated', handleStorageChange);
      };
    }
  }, [isAuthenticated]);

  // Listen for authenticated search updates
  useEffect(() => {
    if (isAuthenticated) {
      const handleSearchUpdate = () => {
        fetchRecentSearches();
      };

      window.addEventListener('searchHistoryUpdated', handleSearchUpdate);

      return () => {
        window.removeEventListener('searchHistoryUpdated', handleSearchUpdate);
      };
    }
  }, [isAuthenticated]);

  const loadGuestSearches = () => {
    try {
      const guestSearches = getGuestSearches();
      // Convert guest searches to display format with temporary IDs
      const displaySearches: DisplaySearchItem[] = guestSearches.map((search, index) => ({
        ...search,
        id: `guest-${index}`,
        search_query: search.query,
        created_at: search.timestamp || new Date().toISOString(),
      }));
      setSearches(displaySearches.slice(0, 3)); // Show only 3 most recent
    } catch (err) {
      logger.error('Error loading guest searches', err as Error);
    } finally {
      setLoading(false);
    }
  };

  const fetchRecentSearches = async () => {
    try {
      const response = await publicApi.getRecentSearches();

      if (response.error) {
        logger.error('Failed to fetch recent searches', new Error(response.error));
        setError('Failed to load recent searches');
        return;
      }

      if (response.data) {
        setSearches(response.data);
      }
    } catch (err) {
      logger.error('Error fetching recent searches', err as Error);
      setError('Failed to load recent searches');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSearch = async (searchId: number | string) => {
    try {
      if (typeof searchId === 'string' && searchId.startsWith('guest-')) {
        // Delete from sessionStorage for guest searches
        const guestSearches = getGuestSearches();
        const index = parseInt(searchId.replace('guest-', ''));
        guestSearches.splice(index, 1);
        sessionStorage.setItem('recentSearches', JSON.stringify(guestSearches));

        // Reload guest searches
        loadGuestSearches();
        logger.info('Guest search deleted successfully', { searchId });
      } else if (typeof searchId === 'number') {
        // Optimistically remove from local state FIRST
        setSearches((prev) => prev.filter((s) => s.id !== searchId));

        // Then delete from database
        const response = await publicApi.deleteSearchHistory(searchId);

        if (response.error) {
          logger.error('Failed to delete search', new Error(response.error));
          // On error, refresh to restore the correct state
          fetchRecentSearches();
          return;
        }

        logger.info('Search deleted successfully', { searchId });
      }
    } catch (err) {
      logger.error('Error deleting search', err as Error);
    }
  };

  // Don't render anything if loading or no searches
  if (loading || searches.length === 0) {
    return null;
  }

  return (
    <section className="py-16 bg-white dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center mb-8">
          <Clock className="h-6 w-6 text-gray-500 dark:text-gray-400 mr-3" />
          <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Your Recent Searches
          </h2>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {searches.map((search) => {
            const encodedQuery = encodeURIComponent(search.search_query);

            return (
              <div
                key={search.id}
                className="group relative bg-gray-50 dark:bg-gray-800 rounded-lg p-4 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              >
                <Link
                  href={`/search?q=${encodedQuery}&from=recent`}
                  className="block"
                  onClick={() => {
                    // Track navigation source
                    if (typeof window !== 'undefined') {
                      sessionStorage.setItem('navigationFrom', 'recent-searches');
                    }
                  }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center mb-1">
                        <Search className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                        <p className="text-gray-900 dark:text-gray-100 font-medium line-clamp-1">
                          {search.search_query}
                        </p>
                      </div>
                      {search.results_count !== null && (
                        <p className="text-sm text-gray-500 dark:text-gray-400 ml-6">
                          {search.results_count} {search.results_count === 1 ? 'result' : 'results'}
                        </p>
                      )}
                    </div>
                  </div>
                </Link>

                {/* Delete button */}
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleDeleteSearch(search.id);
                  }}
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                  aria-label="Remove search"
                >
                  <X className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                </button>
              </div>
            );
          })}
        </div>

        {/* View all searches link */}
        <div className="mt-6 text-center">
          <Link
            href="/search"
            className="inline-flex items-center text-blue-600 dark:text-blue-400 hover:underline"
          >
            <TrendingUp className="h-4 w-4 mr-1" />
            Explore trending searches
          </Link>
        </div>
      </div>
    </section>
  );
}
