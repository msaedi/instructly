// frontend/lib/databaseApi.ts
/**
 * Database monitoring API client for admin dashboard
 */

import { withApiBase } from '@/lib/apiBase';

function apiBaseUrl(): string {
  return withApiBase('/').replace(/\/$/, '');
}

export interface DatabasePool {
  size: number;
  checked_in: number;
  checked_out: number;
  overflow: number;
  total: number;
  max_size: number;
  usage_percent: number;
}

export interface DatabaseStats {
  status: string;
  pool: DatabasePool;
  configuration: {
    pool_size: number;
    max_overflow: number;
    timeout: number;
    recycle: number;
  };
  health: {
    status: string;
    usage_percent: number;
  };
}

/**
 * Fetch with authentication
 */
async function fetchWithAuth<T>(endpoint: string, _token: string | null): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Unauthorized');
    }
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

/**
 * Fetch without authentication (for health endpoint)
 */
async function fetchPublic<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

/**
 * Database monitoring API client
 */
export const databaseApi = {
  /**
   * Get database health status (no auth required)
   */
  async getHealth(): Promise<{ status: string; message: string; pool_status?: unknown }> {
    return fetchPublic('/api/database/health');
  },

  /**
   * Get database statistics (requires admin auth)
   */
  async getStats(token: string): Promise<DatabaseStats> {
    return fetchWithAuth<DatabaseStats>('/api/database/stats', token);
  },

  /**
   * Get database pool status (requires admin auth)
   */
  async getPoolStatus(token: string): Promise<{ status: string; pool: DatabasePool }> {
    return fetchWithAuth('/api/database/pool-status', token);
  },
};
