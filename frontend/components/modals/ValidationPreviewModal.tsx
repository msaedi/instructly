// frontend/components/modals/ValidationPreviewModal.tsx

/**
 * ValidationPreviewModal Component
 *
 * Displays validation results before saving availability changes.
 * Shows conflicts, warnings, and allows user to review or force save.
 *
 * @component
 * @module components/modals
 */

import React from 'react';
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import Modal from '@/components/Modal';
import { WeekValidationResponse, ValidationSlotDetail } from '@/types/availability';
import { logger } from '@/lib/logger';

/**
 * Props for ValidationPreviewModal component
 */
interface ValidationPreviewModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Validation results to display */
  validationResults: WeekValidationResponse | null;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback when save is confirmed */
  onConfirm: () => void;
  /** Whether save operation is in progress */
  isSaving?: boolean;
}

/**
 * Modal for previewing validation results
 *
 * @param {ValidationPreviewModalProps} props - Component props
 * @returns Modal component or null if not open
 *
 * @example
 * ```tsx
 * <ValidationPreviewModal
 *   isOpen={showValidationPreview}
 *   validationResults={validationResults}
 *   onClose={() => setShowValidationPreview(false)}
 *   onConfirm={handleConfirmSave}
 *   isSaving={isSaving}
 * />
 * ```
 */
export default function ValidationPreviewModal({
  isOpen,
  validationResults,
  onClose,
  onConfirm,
  isSaving = false,
}: ValidationPreviewModalProps): React.ReactElement | null {
  if (!isOpen || !validationResults) return null;

  const { valid, summary, details, warnings } = validationResults;

  /**
   * Handle confirm save
   */
  const handleConfirm = () => {
    logger.info('Validation preview confirmed', {
      totalOperations: summary.total_operations,
      conflicts: summary.invalid_operations,
    });
    onConfirm();
  };

  /**
   * Format operation action for display
   */
  const formatAction = (action: string): string => {
    switch (action) {
      case 'add':
        return '+ Add';
      case 'remove':
        return '- Remove';
      case 'update':
        return '↻ Update';
      default:
        return action;
    }
  };

  /**
   * Get icon for operation status
   */
  const getStatusIcon = (detail: ValidationSlotDetail): React.ReactElement => {
    if (detail.reason?.includes('Valid')) {
      return <CheckCircle className="w-4 h-4 text-green-600" />;
    }
    return <XCircle className="w-4 h-4 text-red-600" />;
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={valid ? 'Review Changes' : 'Conflicts Detected'}
      size="lg"
    >
      <div className="p-6">
        <div className="space-y-6 max-h-[60vh] overflow-y-auto">
          {/* Summary */}
          <div className="p-4 bg-gray-50 rounded-lg">
            <h4 className="font-medium text-gray-900 mb-3">Summary</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="font-medium">Total Operations:</span>
                <span className="ml-2">{summary.total_operations}</span>
              </div>
              <div>
                <span className="font-medium">Valid:</span>
                <span className="ml-2 text-green-600">{summary.valid_operations}</span>
              </div>
              <div>
                <span className="font-medium">Conflicts:</span>
                <span className="ml-2 text-red-600">{summary.invalid_operations}</span>
              </div>
              <div>
                <span className="font-medium">Changes:</span>
                <span className="ml-2">
                  +{summary.estimated_changes['slots_added']} / -
                  {summary.estimated_changes['slots_removed']}
                </span>
              </div>
            </div>
          </div>

          {/* Warnings */}
          {warnings.length > 0 && (
            <div className="p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-5 h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="font-medium text-yellow-800 mb-1">Warnings:</p>
                  <ul className="list-disc list-inside text-sm text-yellow-700 space-y-1">
                    {warnings.map((warning, idx) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Conflict Details */}
          {summary.invalid_operations > 0 && (
            <div>
              <h4 className="font-medium mb-2 text-red-600">Conflicts</h4>
              <div className="space-y-2">
                {details
                  .filter((d) => d.reason && !d.reason.includes('Valid'))
                  .map((detail, idx) => (
                    <div key={idx} className="p-3 bg-red-50 border border-red-200 rounded text-sm">
                      <div className="flex items-start gap-2">
                        {getStatusIcon(detail)}
                        <div className="flex-1">
                          <div className="font-medium">
                            {formatAction(detail.action)}
                            {detail.date && ` on ${new Date(detail.date).toLocaleDateString()}`}
                            {detail.start_time &&
                              detail.end_time &&
                              ` ${detail.start_time} - ${detail.end_time}`}
                          </div>
                          <div className="text-red-600 mt-1">{detail.reason}</div>
                          {detail.conflicts_with && detail.conflicts_with.length > 0 && (
                            <div className="text-xs text-gray-600 mt-1">
                              Conflicts with booking(s):{' '}
                              {detail.conflicts_with
                                .map((c) => `${c['start_time']} - ${c['end_time']}`)
                                .join(', ')}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Valid Operations */}
          {summary.valid_operations > 0 && (
            <div>
              <h4 className="font-medium mb-2 text-green-600">Valid Operations</h4>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {details
                  .filter((d) => d.reason && d.reason.includes('Valid'))
                  .map((detail, idx) => (
                    <div
                      key={idx}
                      className="p-2 bg-green-50 rounded text-sm flex items-start gap-2"
                    >
                      {getStatusIcon(detail)}
                      <span>
                        {formatAction(detail.action)}
                        {detail.date && ` on ${new Date(detail.date).toLocaleDateString()}`}
                        {detail.start_time &&
                          detail.end_time &&
                          ` ${detail.start_time} - ${detail.end_time}`}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      </div>
      {/* Action Buttons */}
      <div className="flex gap-3 justify-end mt-6 pt-6 border-t">
        <button
          onClick={onClose}
          disabled={isSaving}
          className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg
                   hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2
                   focus:ring-gray-500 transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
        {valid && (
          <button
            onClick={handleConfirm}
            disabled={isSaving}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700
                     focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500
                     transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {isSaving ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <CheckCircle className="w-4 h-4" />
                <span>Confirm Save</span>
              </>
            )}
          </button>
        )}
      </div>
    </Modal>
  );
}
