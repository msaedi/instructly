import { CheckCircle, XCircle, Server, Cpu, Users } from 'lucide-react';
import type { RedisHealth, RedisStats } from '@/lib/redisApi';

interface StatusCardsProps {
  data: {
    health: RedisHealth | null;
    stats: RedisStats | null;
    testConnection: { status: string; ping: boolean; message?: string } | null;
  };
}

export default function StatusCards({ data }: StatusCardsProps) {
  const isConnected = data.testConnection?.ping === true;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
      {/* Connection Status */}
      <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Connection</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {isConnected ? 'Connected' : 'Disconnected'}
            </p>
          </div>
          {isConnected ? (
            <CheckCircle className="h-8 w-8 text-green-600" />
          ) : (
            <XCircle className="h-8 w-8 text-red-600" />
          )}
        </div>
      </div>

      {/* Redis Version */}
      <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Redis Version</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {data.stats?.server?.redis_version || 'N/A'}
            </p>
          </div>
          <Server className="h-8 w-8 text-blue-600" />
        </div>
      </div>

      {/* Operations/sec */}
      <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Ops/sec</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {data.stats?.operations?.current_ops_per_sec || 0}
            </p>
          </div>
          <Cpu className="h-8 w-8 text-purple-600" />
        </div>
      </div>

      {/* Connected Clients */}
      <div className="rounded-2xl shadow-sm ring-1 ring-gray-200/70 dark:ring-gray-700/60 bg-white/60 dark:bg-gray-900/40 backdrop-blur p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Clients</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {data.stats?.clients?.connected_clients || 0}
            </p>
          </div>
          <Users className="h-8 w-8 text-orange-600" />
        </div>
      </div>
    </div>
  );
}
