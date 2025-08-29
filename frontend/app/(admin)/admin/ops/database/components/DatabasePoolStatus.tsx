import { Database, AlertCircle, CheckCircle } from 'lucide-react';

interface DatabasePoolStatusProps {
  pool?: {
    size: number;
    checked_in: number;
    checked_out: number;
    overflow: number;
    total: number;
    max_size: number;
  };
}

export default function DatabasePoolStatus({ pool }: DatabasePoolStatusProps) {
  if (!pool) {
    return <div className="text-center text-gray-500">No database pool data available</div>;
  }

  const usagePercent = (pool.checked_out / pool.max_size) * 100;
  const isHealthy = usagePercent < 80;

  return (
    <div className="space-y-4">
      {/* Status Alert */}
      <div
        className={`p-4 rounded-xl ring-1 ${
          isHealthy
            ? 'bg-green-50/70 ring-green-200/70 dark:bg-green-900/10 dark:ring-green-800/60'
            : 'bg-red-50/70 ring-red-200/70 dark:bg-red-900/10 dark:ring-red-800/60'
        }`}
      >
        <div className="flex items-center gap-3">
          {isHealthy ? (
            <CheckCircle className="h-6 w-6 text-green-600" />
          ) : (
            <AlertCircle className="h-6 w-6 text-red-600" />
          )}
          <div>
            <p className={`font-medium ${isHealthy ? 'text-green-800' : 'text-red-800'}`}>
              Pool Status: {isHealthy ? 'Healthy' : 'Critical'}
            </p>
            <p className={`text-sm ${isHealthy ? 'text-green-600' : 'text-red-600'}`}>
              {pool.checked_out} of {pool.max_size} connections in use ({usagePercent.toFixed(1)}%)
            </p>
          </div>
        </div>
      </div>

      {/* Connection Breakdown */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-gray-50 dark:bg-gray-800/60 p-4 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Active Connections</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{pool.checked_out}</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Currently in use</p>
        </div>
        <div className="bg-gray-50 dark:bg-gray-800/60 p-4 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">Available Connections</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{pool.checked_in}</p>
          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">Ready to use</p>
        </div>
      </div>

      {/* Pool Configuration */}
      <div className="border-t pt-4">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Pool Configuration
        </h4>
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600 dark:text-gray-400">Base Pool Size</span>
            <span className="text-sm font-mono text-gray-900 dark:text-gray-100">{pool.size}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600 dark:text-gray-400">Overflow Connections</span>
            <span className="text-sm font-mono text-gray-900 dark:text-gray-100">
              {pool.overflow}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600 dark:text-gray-400">Maximum Connections</span>
            <span className="text-sm font-mono text-gray-900 dark:text-gray-100">
              {pool.max_size}
            </span>
          </div>
        </div>
      </div>

      {/* Usage Bar */}
      <div className="mt-4">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-gray-600 dark:text-gray-400">Connection Usage</span>
          <span className="font-medium text-gray-900 dark:text-gray-100">
            {usagePercent.toFixed(1)}%
          </span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
          <div
            className={`h-3 rounded-full transition-all duration-300 ${
              usagePercent < 50
                ? 'bg-green-600'
                : usagePercent < 80
                  ? 'bg-yellow-600'
                  : 'bg-red-600'
            }`}
            style={{ width: `${Math.min(usagePercent, 100)}%` }}
          />
        </div>
      </div>

      {/* Recommendations */}
      {!isHealthy && (
        <div className="mt-4 p-3 bg-yellow-50/80 dark:bg-yellow-900/20 ring-1 ring-yellow-200/70 dark:ring-yellow-800/60 rounded-xl">
          <p className="text-sm text-yellow-800 dark:text-yellow-300 font-medium">
            ⚠️ High Connection Usage
          </p>
          <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-1">
            Consider increasing pool_size and max_overflow in production config
          </p>
        </div>
      )}
    </div>
  );
}
