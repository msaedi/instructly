// frontend/components/modals/DeleteProfileModal.tsx
'use client';

import { useState } from 'react';
import { AlertTriangle, Shield, Trash2 } from 'lucide-react';
import Modal from '@/components/Modal';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import type { ApiErrorResponse } from '@/features/shared/api/types';
import { logger } from '@/lib/logger';

/**
 * DeleteProfileModal Component
 *
 * Modal dialog for deleting an instructor profile with safety confirmation.
 * Updated with professional design system.
 *
 * @component
 */
interface DeleteProfileModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal should close */
  onClose: () => void;
  /** Callback when profile is successfully deleted */
  onSuccess: () => void;
}

export default function DeleteProfileModal({
  isOpen,
  onClose,
  onSuccess,
}: DeleteProfileModalProps) {
  const [confirmText, setConfirmText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  /**
   * Handle profile deletion
   */
  const handleDelete = async () => {
    if (confirmText !== 'DELETE') {
      logger.warn('Delete profile attempted without proper confirmation');
      setError('Please type DELETE to confirm');
      return;
    }

    setLoading(true);
    setError('');

    logger.info('Instructor profile deletion initiated');

    try {
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = (await response.json()) as ApiErrorResponse;
        throw new Error(errorData.detail || errorData.message || 'Failed to delete profile');
      }

      logger.info('Instructor profile deleted successfully');
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const errorMessage = (err as Error)?.message || 'Failed to delete profile. Please try again.';
      logger.error('Failed to delete instructor profile', err as Error);
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // Don't render if not open
  if (!isOpen) return null;

  logger.debug('Delete profile modal opened');

  const isConfirmed = confirmText === 'DELETE';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title=""
      size="md"
      showCloseButton={false}
      footer={
        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={() => {
              logger.debug('Delete profile modal cancelled');
              setConfirmText('');
              setError('');
              onClose();
            }}
            className="px-4 py-2.5 text-gray-700 bg-white border border-gray-300 rounded-lg
                     hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                     focus:ring-gray-500 transition-all duration-150 font-medium"
            disabled={loading}
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            disabled={!isConfirmed || loading}
            className="px-4 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700
                     disabled:opacity-50 disabled:cursor-not-allowed transition-all
                     duration-150 font-medium focus:outline-none focus:ring-2
                     focus:ring-offset-2 focus:ring-red-500 flex items-center gap-2"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                <span>Deleting...</span>
              </>
            ) : (
              <>
                <Trash2 className="w-4 h-4" />
                <span>Delete Profile</span>
              </>
            )}
          </button>
        </div>
      }
    >
      <div className="space-y-6">
        {/* Header with Icon */}
        <div className="flex flex-col items-center text-center">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
            <AlertTriangle className="w-8 h-8 text-red-600" />
          </div>
          <h3 className="text-xl font-semibold text-gray-900">Delete Instructor Profile</h3>
          <p className="mt-2 text-gray-600">This action cannot be undone</p>
        </div>

        {/* Consequences Warning */}
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h4 className="text-sm font-medium text-red-900 mb-3">This will permanently delete:</h4>
          <ul className="space-y-2 text-sm text-red-700">
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              <span>Your instructor profile and bio</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              <span>All your services and rates</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              <span>Your availability schedule</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              <span>All pending and future bookings</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              <span>Your instructor reviews and ratings</span>
            </li>
          </ul>
        </div>

        {/* Note about Student Account */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-start gap-3">
          <Shield className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm text-blue-900 font-medium">Student Account Preserved</p>
            <p className="text-sm text-blue-700 mt-1">
              You will remain a student and can continue booking lessons. You can always become an
              instructor again later.
            </p>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Confirmation Input */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Type <span className="font-mono font-bold text-red-600">DELETE</span> to confirm
          </label>
          <input
            type="text"
            value={confirmText}
            onChange={(e) => {
              setConfirmText(e.target.value);
              setError(''); // Clear error when typing
            }}
            className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2
                       focus:ring-offset-2 transition-colors font-mono ${
                         isConfirmed
                           ? 'border-green-300 focus:ring-green-500 bg-green-50'
                           : 'border-gray-300 focus:ring-red-500'
                       }`}
            placeholder="Type DELETE here"
            disabled={loading}
            aria-describedby="delete-confirmation-help"
          />
          <p id="delete-confirmation-help" className="mt-2 text-xs text-gray-500">
            This confirmation is case-sensitive
          </p>
        </div>
      </div>
    </Modal>
  );
}
