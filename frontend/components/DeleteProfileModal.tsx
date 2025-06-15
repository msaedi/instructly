// frontend/components/DeleteProfileModal.tsx
"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { logger } from '@/lib/logger';

/**
 * DeleteProfileModal Component
 * 
 * Modal dialog for deleting an instructor profile with safety confirmation.
 * Requires typing "DELETE" to confirm the destructive action.
 * 
 * Features:
 * - Destructive action confirmation pattern
 * - Clear warning about data loss
 * - Type-to-confirm safety mechanism
 * - Loading and error states
 * - Detailed consequences explanation
 * 
 * @component
 * @example
 * ```tsx
 * <DeleteProfileModal
 *   isOpen={showDeleteModal}
 *   onClose={() => setShowDeleteModal(false)}
 *   onSuccess={handleProfileDeleted}
 * />
 * ```
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
  onSuccess 
}: DeleteProfileModalProps) {
  const [confirmText, setConfirmText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  /**
   * Handle profile deletion
   */
  const handleDelete = async () => {
    if (confirmText !== "DELETE") {
      logger.warn('Delete profile attempted without proper confirmation');
      return;
    }

    setLoading(true);
    setError("");

    logger.info('Instructor profile deletion initiated');

    try {
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE, {
        method: "DELETE",
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to delete profile");
      }

      logger.info('Instructor profile deleted successfully');
      onSuccess();
      onClose();
    } catch (err: any) {
      const errorMessage = err.message || "Failed to delete profile. Please try again.";
      logger.error('Failed to delete instructor profile', err);
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  // Don't render if not open
  if (!isOpen) return null;

  logger.debug('Delete profile modal opened');

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg max-w-md w-full">
        <div className="p-6">
          {/* Header with warning icon */}
          <div className="flex items-center mb-4">
            <AlertTriangle className="text-red-500 mr-3" size={32} />
            <h2 className="text-xl font-bold text-gray-900">Delete Instructor Profile</h2>
          </div>

          <div className="mb-6 space-y-4">
            <p className="text-gray-700">
              Are you sure you want to delete your instructor profile? This action cannot be undone.
            </p>
            
            {/* Consequences warning */}
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <p className="text-sm text-red-800 font-semibold mb-2">
                Warning: This will permanently delete:
              </p>
              <ul className="list-disc list-inside text-sm text-red-700 space-y-1">
                <li>Your instructor profile and bio</li>
                <li>All your services and rates</li>
                <li>Your availability schedule</li>
                <li>All pending and future bookings</li>
                <li>Your instructor reviews and ratings</li>
              </ul>
            </div>

            {/* Note about student account */}
            <div className="bg-blue-50 border border-blue-200 rounded-md p-4">
              <p className="text-sm text-blue-800">
                <strong>Note:</strong> You will remain a student and can continue booking lessons. 
                You can always become an instructor again later.
              </p>
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded text-sm">
              {error}
            </div>
          )}

          {/* Confirmation input */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Type <span className="font-bold">DELETE</span> to confirm
            </label>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500"
              placeholder="Type DELETE here"
              disabled={loading}
              aria-describedby="delete-confirmation-help"
            />
            <p id="delete-confirmation-help" className="mt-1 text-xs text-gray-500">
              This confirmation is case-sensitive
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex justify-end space-x-3">
            <button
              type="button"
              onClick={() => {
                logger.debug('Delete profile modal cancelled');
                onClose();
              }}
              className="px-4 py-2 text-gray-700 bg-gray-200 rounded-md hover:bg-gray-300 transition-colors"
              disabled={loading}
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={confirmText !== "DELETE" || loading}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Deleting..." : "Delete Profile"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}