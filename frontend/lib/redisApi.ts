// frontend/lib/redisApi.ts
/**
 * Redis monitoring API client for admin dashboard
 */

import { withApiBase } from '@/lib/apiBase';
import type {
  RedisHealthResponse,
  RedisStatsResponse,
  RedisCeleryQueuesResponse,
  RedisConnectionAuditResponse,
  RedisTestResponse,
} from '@/features/shared/api/types';

function apiBaseUrl(): string {
  return withApiBase('/').replace(/\/$/, '');
}

// Re-export types for consumers
export type {
  RedisHealthResponse,
  RedisStatsResponse,
  RedisCeleryQueuesResponse,
  RedisConnectionAuditResponse,
  RedisTestResponse,
};

export type RedisHealth = RedisHealthResponse;
export interface RedisStats {
  server?: {
    redis_version?: string;
    uptime_in_days?: number;
  };
  clients?: {
    connected_clients?: number;
  };
  operations?: {
    current_ops_per_sec?: number;
    estimated_daily_ops?: number;
    total_commands_processed?: number;
  };
  memory?: {
    used_memory_human?: string;
    used_memory_peak_human?: string;
    used_memory_rss_human?: string;
    maxmemory_human?: string;
    mem_fragmentation_ratio?: number;
  };
}

export interface CeleryQueues {
  queues: Record<string, number>;
  total_pending: number;
}

export interface ConnectionAudit {
  service_connections?: {
    api_service?: { host?: string; type?: string };
    celery_broker?: { host?: string; type?: string };
  };
  active_connections?: {
    local_redis?: number;
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
 * Redis monitoring API client
 */
export const redisApi = {
  /**
   * Get Redis health status (no auth required)
   */
  async getHealth(): Promise<RedisHealthResponse> {
    return fetchPublic<RedisHealthResponse>('/api/v1/redis/health');
  },

  /**
   * Get Redis statistics (requires admin auth)
   */
  async getStats(token: string): Promise<RedisStats> {
    const response = await fetchWithAuth<RedisStatsResponse>('/api/v1/redis/stats', token);
    const stats = response.stats;
    return typeof stats === 'object' && stats
      ? (stats as RedisStats)
      : {};
  },

  /**
   * Get Celery queue status (requires admin auth)
   */
  async getCeleryQueues(token: string): Promise<CeleryQueues> {
    const response = await fetchWithAuth<RedisCeleryQueuesResponse>('/api/v1/redis/celery-queues', token);
    return {
      queues: response.queues.queues ?? {},
      total_pending: response.queues.total_pending,
    };
  },

  /**
   * Get Redis test connection (no auth required)
   */
  async testConnection(): Promise<RedisTestResponse> {
    return fetchPublic<RedisTestResponse>('/api/v1/redis/test');
  },

  /**
   * Get Redis connection audit (requires admin auth)
   */
  async getConnectionAudit(token: string): Promise<ConnectionAudit | null> {
    const response = await fetchWithAuth<RedisConnectionAuditResponse>('/api/v1/redis/connection-audit', token);
    const connection = Array.isArray(response.connections) ? response.connections[0] : null;
    if (connection && typeof connection === 'object') {
      return connection as ConnectionAudit;
    }
    return null;
  },
};
