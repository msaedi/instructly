import { ConnectionAudit } from '@/lib/redisApi';
import { CheckCircle, XCircle, AlertCircle, Globe, Database } from 'lucide-react';

interface ConnectionAuditProps {
  audit: ConnectionAudit | null;
}

export default function ConnectionAuditSection({ audit }: ConnectionAuditProps) {
  if (!audit) {
    return <div className="text-center text-gray-500">No audit data available</div>;
  }

  const isFullyMigrated = audit.migration_status === 'complete';

  return (
    <div className="space-y-6">
      {/* Migration Status */}
      <div
        className={`p-4 rounded-lg ${
          isFullyMigrated
            ? 'bg-green-50 border border-green-200'
            : 'bg-yellow-50 border border-yellow-200'
        }`}
      >
        <div className="flex items-center gap-3">
          {isFullyMigrated ? (
            <CheckCircle className="h-6 w-6 text-green-600" />
          ) : (
            <AlertCircle className="h-6 w-6 text-yellow-600" />
          )}
          <div>
            <p className={`font-medium ${isFullyMigrated ? 'text-green-800' : 'text-yellow-800'}`}>
              Migration Status: {audit.migration_status === 'complete' ? 'Complete' : 'In Progress'}
            </p>
            <p className={`text-sm ${isFullyMigrated ? 'text-green-600' : 'text-yellow-600'}`}>
              {audit.recommendation}
            </p>
          </div>
        </div>
      </div>

      {/* Service Connections */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 mb-3">Service Connections</h4>
        <div className="space-y-3">
          {/* API Service */}
          <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-3">
              <Globe className="h-5 w-5 text-blue-600" />
              <div>
                <p className="font-medium">API Cache</p>
                <p className="text-sm text-gray-600">
                  {audit.service_connections.api_service.host}
                </p>
              </div>
            </div>
            <span
              className={`px-2 py-1 text-xs rounded-full ${
                audit.service_connections.api_service.type === 'render_redis'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {audit.service_connections.api_service.type}
            </span>
          </div>

          {/* Celery Broker */}
          <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
            <div className="flex items-center gap-3">
              <Database className="h-5 w-5 text-purple-600" />
              <div>
                <p className="font-medium">Celery Broker</p>
                <p className="text-sm text-gray-600">
                  {audit.service_connections.celery_broker.host}
                </p>
              </div>
            </div>
            <span
              className={`px-2 py-1 text-xs rounded-full ${
                audit.service_connections.celery_broker.type === 'render_redis'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {audit.service_connections.celery_broker.type}
            </span>
          </div>
        </div>
      </div>

      {/* Active Connections */}
      <div>
        <h4 className="text-sm font-medium text-gray-700 mb-3">Active Connections</h4>
        <div className="grid grid-cols-2 gap-4">
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-600">Render Redis</p>
            <p className="text-2xl font-bold text-gray-900">
              {audit.active_connections.local_redis}
            </p>
          </div>
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-600">Upstash</p>
            <p className="text-2xl font-bold text-gray-900">{audit.active_connections.upstash}</p>
          </div>
        </div>
      </div>

      {/* Environment Variables */}
      {audit.upstash_detected && (
        <div className="border-t pt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Environment Check</h4>
          <div className="space-y-2">
            {Object.entries(audit.environment_variables).map(([key, value]) => (
              <div key={key} className="flex justify-between items-center">
                <span className="text-sm font-mono text-gray-600">{key}</span>
                <span
                  className={`text-sm font-mono ${
                    value.includes('upstash') ? 'text-red-600' : 'text-gray-900'
                  }`}
                >
                  {value.length > 40 ? value.substring(0, 40) + '...' : value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upstash Detection Warning */}
      {audit.upstash_detected && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-center gap-2">
            <XCircle className="h-5 w-5 text-red-600" />
            <div>
              <p className="font-medium text-red-800">Upstash Configuration Detected</p>
              <p className="text-sm text-red-600 mt-1">
                Remove UPSTASH_URL from environment variables to complete migration
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
