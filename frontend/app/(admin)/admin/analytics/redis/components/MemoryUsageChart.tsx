import { RedisStats } from '@/lib/redisApi';

interface MemoryUsageChartProps {
  stats: RedisStats | null;
}

export default function MemoryUsageChart({ stats }: MemoryUsageChartProps) {
  if (!stats || !stats.memory) {
    return <div className="text-center text-gray-500">No data available</div>;
  }

  const memoryData = [
    { label: 'Used Memory', value: stats.memory.used_memory_human || 'N/A', color: 'bg-blue-500' },
    {
      label: 'Peak Memory',
      value: stats.memory.used_memory_peak_human || 'N/A',
      color: 'bg-purple-500',
    },
    {
      label: 'RSS Memory',
      value: stats.memory.used_memory_rss_human || 'N/A',
      color: 'bg-orange-500',
    },
  ];

  // Parse memory values to get numeric values for percentage calculation
  const parseMemory = (value: string): number => {
    const match = value.match(/(\d+\.?\d*)/);
    if (!match) return 0;

    const num = parseFloat(match[1]);
    if (value.includes('G')) return num * 1024;
    if (value.includes('M')) return num;
    if (value.includes('K')) return num / 1024;
    return num;
  };

  const maxMemory = parseMemory(stats.memory.maxmemory_human || '256M');
  const usedMemory = parseMemory(stats.memory.used_memory_human);
  const usedPercentage = maxMemory > 0 ? (usedMemory / maxMemory) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Memory Usage Bar */}
      <div>
        <div className="flex justify-between mb-2">
          <span className="text-sm font-medium">Memory Usage</span>
          <span className="text-sm text-gray-600">
            {stats.memory.used_memory_human} / {stats.memory.maxmemory_human || '256M'}
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-4">
          <div
            className={`h-4 rounded-full transition-all duration-300 ${
              usedPercentage > 90
                ? 'bg-red-500'
                : usedPercentage > 70
                  ? 'bg-yellow-500'
                  : 'bg-green-500'
            }`}
            style={{ width: `${Math.min(usedPercentage, 100)}%` }}
          />
        </div>
        <div className="mt-1 text-xs text-gray-600">{usedPercentage.toFixed(1)}% used</div>
      </div>

      {/* Memory Details */}
      <div className="space-y-3">
        {memoryData.map((item) => (
          <div key={item.label} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${item.color}`} />
              <span className="text-sm">{item.label}</span>
            </div>
            <span className="text-sm font-medium">{item.value}</span>
          </div>
        ))}
      </div>

      {/* Fragmentation Ratio */}
      <div className="pt-4 border-t">
        <div className="flex justify-between items-center">
          <span className="text-sm">Memory Fragmentation Ratio</span>
          <span
            className={`text-sm font-medium ${
              (stats.memory.mem_fragmentation_ratio || 1) > 1.5 ? 'text-red-600' : 'text-green-600'
            }`}
          >
            {(stats.memory.mem_fragmentation_ratio || 1).toFixed(2)}
          </span>
        </div>
        <p className="text-xs text-gray-600 mt-1">
          {(stats.memory.mem_fragmentation_ratio || 1) > 1.5
            ? 'High fragmentation - consider restarting Redis'
            : 'Fragmentation is within normal range'}
        </p>
      </div>
    </div>
  );
}
