// frontend/lib/databaseApi.ts
/**
 * Database monitoring API client for admin dashboard
 */

import { withApiBase } from '@/lib/apiBase';
import type {
  DatabaseHealthResponse,
  DatabaseStatsResponse,
  DatabasePoolStatusResponse,
} from '@/features/shared/api/types';

function apiBaseUrl(): string {
  return withApiBase('/').replace(/\/$/, '');
}

// Re-export types for consumers
export type {
  DatabaseHealthResponse,
  DatabaseStatsResponse,
  DatabasePoolStatusResponse,
};

export type DatabaseHealth = DatabaseHealthResponse;
export type DatabasePoolStatus = DatabasePoolStatusResponse;

export interface DatabasePoolMetrics {
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
  pool?: DatabasePoolMetrics;
  configuration?: Record<string, unknown>;
  health?: Record<string, unknown>;
}

function toNumber(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
}

function normalizePool(raw: Record<string, unknown> | undefined): DatabasePoolMetrics | undefined {
  if (!raw || typeof raw !== 'object') return undefined;
  const size = toNumber(raw['size']);
  const checked_in = toNumber(raw['checked_in']);
  const checked_out = toNumber(raw['checked_out']);
  const overflow = toNumber(raw['overflow']);
  const total = toNumber(raw['total']);
  const max_size = toNumber(raw['max_size']);
  const usage_percent =
    typeof raw['usage_percent'] === 'number'
      ? (raw['usage_percent'] as number)
      : max_size > 0
        ? Math.round((checked_out / max_size) * 1000) / 10
        : 0;
  return {
    size,
    checked_in,
    checked_out,
    overflow,
    total,
    max_size,
    usage_percent,
  };
}

function normalizeStats(response: DatabaseStatsResponse): DatabaseStats {
  const pool = normalizePool(response.pool as Record<string, unknown> | undefined);
  const configuration =
    response.configuration && typeof response.configuration === 'object'
      ? (response.configuration as Record<string, unknown>)
      : undefined;
  const health =
    response.health && typeof response.health === 'object'
      ? (response.health as Record<string, unknown>)
      : undefined;
  const stats: DatabaseStats = {
    status: response.status,
  };
  if (pool) {
    stats.pool = pool;
  }
  if (configuration) {
    stats.configuration = configuration;
  }
  if (health) {
    stats.health = health;
  }
  return stats;
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

  return (await response.json()) as T;
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

  return (await response.json()) as T;
}

/**
 * Database monitoring API client
 */
export const databaseApi = {
  /**
   * Get database health status (no auth required)
   */
  async getHealth(): Promise<DatabaseHealthResponse> {
    return fetchPublic<DatabaseHealthResponse>('/api/v1/database/health');
  },

  /**
   * Get database statistics (requires admin auth)
   */
  async getStats(token: string): Promise<DatabaseStats> {
    const response = await fetchWithAuth<DatabaseStatsResponse>('/api/v1/database/stats', token);
    return normalizeStats(response);
  },

  /**
   * Get database pool status (requires admin auth)
   */
  async getPoolStatus(token: string): Promise<DatabasePoolStatusResponse> {
    return fetchWithAuth<DatabasePoolStatusResponse>('/api/v1/database/pool-status', token);
  },
};
