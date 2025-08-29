import { RedisStats } from '@/lib/redisApi';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';

interface OperationsMetricsProps {
  stats: RedisStats | null;
}

export default function OperationsMetrics({ stats }: OperationsMetricsProps) {
  if (!stats || !stats.operations) {
    return <div className="text-center text-gray-500">No data available</div>;
  }

  const opsPerSec = stats.operations.current_ops_per_sec || 0;
  const dailyOps = stats.operations.estimated_daily_ops || 0;
  const totalCommands = stats.operations.total_commands_processed || 0;

  // Calculate if operations are within target
  const targetDailyOps = 100000;
  const opsPercentage = (dailyOps / targetDailyOps) * 100;
  const isWithinTarget = dailyOps < targetDailyOps;

  return (
    <div className="space-y-6">
      {/* Current Operations */}
      <div className="text-center p-6 rounded-xl bg-gradient-to-b from-indigo-50 to-white dark:from-indigo-900/10 dark:to-transparent ring-1 ring-gray-200/70 dark:ring-gray-700/60">
        <Activity className="h-8 w-8 mx-auto mb-2 text-indigo-600" />
        <p className="text-sm text-gray-600 mb-1">Current Operations/sec</p>
        <p className="text-4xl font-bold">{opsPerSec.toLocaleString()}</p>
      </div>

      {/* Daily Operations Projection */}
      <div>
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium">Daily Operations Projection</span>
          {isWithinTarget ? (
            <TrendingDown className="h-4 w-4 text-green-600" />
          ) : (
            <TrendingUp className="h-4 w-4 text-red-600" />
          )}
        </div>
        <div className="text-2xl font-bold mb-1">{dailyOps.toLocaleString()}</div>
        <div className="text-sm text-gray-600">
          Target: {targetDailyOps.toLocaleString()} ops/day
        </div>
        <div className="mt-2">
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all duration-300 ${
                isWithinTarget ? 'bg-green-500' : 'bg-red-500'
              }`}
              style={{ width: `${Math.min(opsPercentage, 100)}%` }}
            />
          </div>
          <p className={`text-xs mt-1 ${isWithinTarget ? 'text-green-600' : 'text-red-600'}`}>
            {opsPercentage.toFixed(1)}% of target
          </p>
        </div>
      </div>

      {/* Total Commands Processed */}
      <div className="pt-4 border-t">
        <div className="flex justify-between items-center">
          <span className="text-sm">Total Commands Processed</span>
          <span className="text-lg font-medium">{totalCommands.toLocaleString()}</span>
        </div>
        <p className="text-xs text-gray-600 mt-1">
          Since server start ({stats.server?.uptime_in_days?.toFixed(1) || '0'} days ago)
        </p>
      </div>

      {/* Performance Status */}
      <div className={`p-4 rounded-xl ring-1 ${
        isWithinTarget
          ? 'bg-green-50/70 ring-green-200/70 dark:bg-green-900/10 dark:ring-green-800/60'
          : 'bg-red-50/70 ring-red-200/70 dark:bg-red-900/10 dark:ring-red-800/60'
      }`}>
        <div className="flex items-center gap-2">
          {isWithinTarget ? (
            <>
              <TrendingDown className="h-5 w-5 text-green-600" />
              <div>
                <p className="font-medium text-green-800">Operations Optimized</p>
                <p className="text-sm text-green-600">
                  Redis operations are {(100 - opsPercentage).toFixed(1)}% below target
                </p>
              </div>
            </>
          ) : (
            <>
              <TrendingUp className="h-5 w-5 text-red-600" />
              <div>
                <p className="font-medium text-red-800">Operations Exceed Target</p>
                <p className="text-sm text-red-600">
                  Redis operations are {(opsPercentage - 100).toFixed(1)}% above target
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
