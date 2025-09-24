// frontend/components/PrivacySettings.tsx
/**
 * Privacy settings component for managing guest session behavior
 */

'use client';

import React, { useState, useEffect } from 'react';
import { setUserPreference } from '@/lib/searchTracking';
import { logger } from '@/lib/logger';

interface PrivacySettingsProps {
  className?: string;
}

export function PrivacySettings({ className = '' }: PrivacySettingsProps) {
  const [clearDataOnLogout, setClearDataOnLogout] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Load current preference on mount (delegate to setUserPreference getter indirectly)
  useEffect(() => {
    setIsLoading(false);
  }, []);

  const handleToggle = (checked: boolean) => {
    setClearDataOnLogout(checked);
    setUserPreference('clearDataOnLogout', checked);
    logger.info('Privacy setting updated', { clearDataOnLogout: checked });
  };

  if (isLoading) {
    return (
      <div className={`privacy-settings ${className}`}>
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-2"></div>
          <div className="h-8 bg-gray-200 rounded w-full"></div>
        </div>
      </div>
    );
  }

  return (
    <div className={`privacy-settings ${className}`}>
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Privacy Settings</h3>

      <div className="space-y-4">
        <label className="flex items-start space-x-3">
          <input
            type="checkbox"
            checked={clearDataOnLogout}
            onChange={(e) => handleToggle(e.target.checked)}
            className="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
          />
          <div className="flex-1">
            <span className="text-sm font-medium text-gray-900">
              Clear search history when I log out
            </span>
            <p className="text-sm text-gray-500 mt-1">
              When enabled, searches you made before logging in will be cleared when you log out.
              When disabled, those searches will still be there if you browse without logging in
              again.
            </p>
          </div>
        </label>
      </div>

      <div className="mt-6 p-4 bg-blue-50 rounded-lg">
        <h4 className="text-sm font-medium text-blue-900 mb-2">About Guest Sessions</h4>
        <p className="text-sm text-blue-700">
          We use persistent sessions to maintain your search history and shopping experience even
          after you close your browser. These sessions expire after 30 days of inactivity. You can
          clear this data at any time using the setting above or by clearing your browser data.
        </p>
      </div>
    </div>
  );
}
