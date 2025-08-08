import { ConnectionAudit } from '@/lib/redisApi';
import { CheckCircle, XCircle, AlertCircle, Globe, Database } from 'lucide-react';

interface ConnectionAuditProps {
  audit: ConnectionAudit | null;
}

export default function ConnectionAuditSection({ audit }: ConnectionAuditProps) {
  if (!audit) {
    return <div className="text-center text-gray-500">No audit data available</div>;
  }

  const apiService = audit.service_connections?.api_service;
  const celeryBroker = audit.service_connections?.celery_broker;
  const activeLocal = audit.active_connections?.local_redis ?? 0;

  return (
    <div className="space-y-6">
      {/* Migration Status */}
      <div className="p-4 rounded-xl bg-green-50/70 ring-1 ring-green-200/70 dark:bg-green-900/10 dark:ring-green-800/60">
        <div className="flex items-center gap-3">
          <CheckCircle className="h-6 w-6 text-green-600" />
          <div>
            <p className="font-medium text-green-800">Redis Migration Complete</p>
            <p className="text-sm text-green-600">
              All services using single Redis instance (Render Redis)
            </p>
          </div>
        </div>
      </div>

      {/* Service Connections */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Service Connections</h4>
        <div className="space-y-3">
          {/* API Service */}
          <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/60 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
            <div className="flex items-center gap-3">
              <Globe className="h-5 w-5 text-blue-600" />
              <div>
                <p className="font-medium">API Cache</p>
                <p className="text-sm text-gray-600">
                  {apiService?.host || 'Unknown'}
                </p>
              </div>
            </div>
            <span
              className={`px-2 py-1 text-xs rounded-full ${
                apiService?.type === 'render_redis'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {apiService?.type || 'unknown'}
            </span>
          </div>

          {/* Celery Broker */}
          <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800/60 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
            <div className="flex items-center gap-3">
              <Database className="h-5 w-5 text-purple-600" />
              <div>
                <p className="font-medium">Celery Broker</p>
                <p className="text-sm text-gray-600">
                  {celeryBroker?.host || 'Unknown'}
                </p>
              </div>
            </div>
            <span
              className={`px-2 py-1 text-xs rounded-full ${
                celeryBroker?.type === 'render_redis'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {celeryBroker?.type || 'unknown'}
            </span>
          </div>
        </div>
      </div>

      {/* Active Connections */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Active Connections</h4>
        <div className="text-center p-4 bg-gray-50 dark:bg-gray-800/60 rounded-xl ring-1 ring-gray-200/70 dark:ring-gray-700/60">
          <p className="text-sm text-gray-600">Render Redis</p>
          <p className="text-2xl font-bold text-gray-900">{activeLocal}</p>
        </div>
      </div>
    </div>
  );
}
