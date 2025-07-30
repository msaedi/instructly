// frontend/lib/redisApi.ts
/**
 * Redis monitoring API client for admin dashboard
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface RedisHealth {
  status: 'healthy' | 'unhealthy';
  connected: boolean;
  error?: string;
}

export interface RedisStats {
  status: string;
  server: {
    redis_version: string;
    uptime_in_seconds: number;
    uptime_in_days: number;
  };
  memory: {
    used_memory_human: string;
    used_memory_peak_human: string;
    used_memory_rss_human: string;
    maxmemory_human: string;
    mem_fragmentation_ratio: number;
  };
  clients: {
    connected_clients: number;
    blocked_clients: number;
  };
  operations: {
    total_commands_processed: number;
    instantaneous_ops_per_sec: number;
    current_ops_per_sec: number;
    estimated_daily_ops: number;
  };
}

export interface CeleryQueues {
  status: string;
  queues: Record<string, number>;
  total_pending: number;
}

export interface ConnectionAudit {
  api_cache: string;
  celery_broker: string;
  active_connections: {
    local_redis: number;
    upstash: number;
  };
  upstash_detected: boolean;
  service_connections: {
    api_service: {
      url: string;
      host: string;
      type: string;
    };
    celery_broker: {
      url: string;
      host: string;
      type: string;
    };
  };
  environment_variables: Record<string, string>;
  migration_status: string;
  recommendation: string;
}

/**
 * Fetch with authentication
 */
async function fetchWithAuth<T>(endpoint: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
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
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
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
 * Redis monitoring API client
 */
export const redisApi = {
  /**
   * Get Redis health status (no auth required)
   */
  async getHealth(): Promise<RedisHealth> {
    return fetchPublic<RedisHealth>('/api/redis/health');
  },

  /**
   * Get Redis statistics (requires admin auth)
   */
  async getStats(token: string): Promise<RedisStats> {
    return fetchWithAuth<RedisStats>('/api/redis/stats', token);
  },

  /**
   * Get Celery queue status (requires admin auth)
   */
  async getCeleryQueues(token: string): Promise<CeleryQueues> {
    return fetchWithAuth<CeleryQueues>('/api/redis/celery-queues', token);
  },

  /**
   * Get Redis test connection (no auth required)
   */
  async testConnection(): Promise<{
    status: string;
    ping: boolean;
    redis_version?: string;
    uptime_seconds?: number;
    connected_clients?: number;
    message: string;
    error?: string;
  }> {
    return fetchPublic('/api/redis/test');
  },

  /**
   * Get Redis connection audit (requires admin auth)
   */
  async getConnectionAudit(token: string): Promise<ConnectionAudit> {
    return fetchWithAuth<ConnectionAudit>('/api/redis/connection-audit', token);
  },
};
