import { CeleryQueues } from '@/lib/redisApi';
import { BarChart3 } from 'lucide-react';

interface CeleryQueuesChartProps {
  queues: CeleryQueues | null;
}

const QUEUE_COLORS: Record<string, string> = {
  celery: 'bg-blue-500',
  email: 'bg-green-500',
  notifications: 'bg-purple-500',
  analytics: 'bg-orange-500',
  maintenance: 'bg-yellow-500',
  bookings: 'bg-pink-500',
  cache: 'bg-indigo-500',
};

export default function CeleryQueuesChart({ queues }: CeleryQueuesChartProps) {
  if (!queues || !queues.queues) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500">
        <BarChart3 className="h-12 w-12 mb-2 opacity-50" />
        <p>No queue data available</p>
      </div>
    );
  }

  const queueEntries = Object.entries(queues.queues).filter(([_, length]) => length >= 0);
  const maxQueueLength = Math.max(...queueEntries.map(([_, length]) => length), 1);

  if (queueEntries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-500">
        <BarChart3 className="h-12 w-12 mb-2 opacity-50" />
        <p>All queues are empty</p>
        <p className="text-sm mt-1">No pending tasks</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Queue Bars */}
      <div className="space-y-4">
        {queueEntries.map(([queueName, length]) => (
          <div key={queueName}>
            <div className="flex justify-between mb-1">
              <span className="text-sm font-medium capitalize">{queueName}</span>
              <span className="text-sm text-gray-600">{length} tasks</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-6">
              <div
                className={`h-6 rounded-full transition-all duration-300 ${
                  QUEUE_COLORS[queueName] || 'bg-gray-500'
                }`}
                style={{
                  width: `${(length / maxQueueLength) * 100}%`,
                  minWidth: length > 0 ? '2%' : '0%',
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="pt-4 border-t">
        <div className="flex justify-between items-center">
          <span className="text-sm font-medium">Total Pending Tasks</span>
          <span className="text-2xl font-bold">{queues.total_pending}</span>
        </div>
        {queues.total_pending > 100 && (
          <p className="text-sm text-yellow-600 mt-2">
            ⚠️ High number of pending tasks - check worker capacity
          </p>
        )}
      </div>

      {/* Queue Health Indicators */}
      <div className="grid grid-cols-2 gap-4 pt-4">
        <div className="text-center p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600">Active Queues</p>
          <p className="text-xl font-bold">
            {queueEntries.filter(([_, length]) => length > 0).length}
          </p>
        </div>
        <div className="text-center p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600">Empty Queues</p>
          <p className="text-xl font-bold">
            {queueEntries.filter(([_, length]) => length === 0).length}
          </p>
        </div>
      </div>
    </div>
  );
}
