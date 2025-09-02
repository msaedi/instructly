/**
 * Favorites API Service
 *
 * Handles all API calls related to favoriting/unfavoriting instructors.
 * All endpoints require authentication.
 */

import { fetchWithAuth } from '@/lib/api';
import { FavoritesListResponse } from '@/types/instructor';

/**
 * Response from add/remove favorite operations
 */
interface FavoriteOperationResponse {
  success: boolean;
  message: string;
  favorite_id?: string;
  already_favorited?: boolean;
  not_favorited?: boolean;
}

/**
 * Response from favorite status check
 */
interface FavoriteStatusResponse {
  is_favorited: boolean;
}

/**
 * Favorites API service
 */
export const favoritesApi = {
  /**
   * Add an instructor to favorites
   * @param instructorId - ULID of the instructor to favorite
   * @returns Promise with operation result
   */
  add: async (instructorId: string): Promise<FavoriteOperationResponse> => {
    const response = await fetchWithAuth(`/api/favorites/${instructorId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return response.json();
  },

  /**
   * Remove an instructor from favorites
   * @param instructorId - ULID of the instructor to unfavorite
   * @returns Promise with operation result
   */
  remove: async (instructorId: string): Promise<FavoriteOperationResponse> => {
    const response = await fetchWithAuth(`/api/favorites/${instructorId}`, {
      method: 'DELETE',
    });
    return response.json();
  },

  /**
   * Get list of all favorited instructors
   * @returns Promise with list of favorited instructors
   */
  list: async (): Promise<FavoritesListResponse> => {
    const response = await fetchWithAuth('/api/favorites');
    return response.json();
  },

  /**
   * Check if a specific instructor is favorited
   * @param instructorId - ULID of the instructor to check
   * @returns Promise with favorite status
   */
  check: async (instructorId: string): Promise<FavoriteStatusResponse> => {
    const response = await fetchWithAuth(`/api/favorites/check/${instructorId}`);
    return response.json();
  },

  /**
   * Toggle favorite status for an instructor
   * @param instructorId - ULID of the instructor
   * @param currentStatus - Current favorite status
   * @returns Promise with operation result
   */
  toggle: async (instructorId: string, currentStatus: boolean): Promise<FavoriteOperationResponse> => {
    if (currentStatus) {
      return favoritesApi.remove(instructorId);
    } else {
      return favoritesApi.add(instructorId);
    }
  }
};
