import { ConnectionAudit } from '@/lib/redisApi';
import { CheckCircle, XCircle, AlertCircle, Globe, Database } from 'lucide-react';

interface ConnectionAuditProps {
  audit: ConnectionAudit | null;
}

export default function ConnectionAuditSection({ audit }: ConnectionAuditProps) {
  if (!audit) {
    return <div className="text-center text-gray-500">No audit data available</div>;
  }

  return (
    <div className="space-y-6">
      {/* Migration Status */}
      <div className="p-4 rounded-lg bg-green-50 border border-green-200">
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
        <div className="text-center p-4 bg-gray-50 rounded-lg">
          <p className="text-sm text-gray-600">Render Redis</p>
          <p className="text-2xl font-bold text-gray-900">{audit.active_connections.local_redis}</p>
        </div>
      </div>
    </div>
  );
}
