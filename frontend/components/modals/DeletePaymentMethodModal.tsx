import React, { useState } from 'react';
import { AlertTriangle, CreditCard, Loader2 } from 'lucide-react';
import Modal from '@/components/Modal';
import { logger } from '@/lib/logger';

interface PaymentMethod {
  id: string;
  last4: string;
  brand: string;
  is_default: boolean;
}

interface DeletePaymentMethodModalProps {
  /** The payment method to delete */
  paymentMethod: PaymentMethod | null;
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal should close */
  onClose: () => void;
  /** Callback when deletion is confirmed */
  onConfirm: () => Promise<void>;
}

export const DeletePaymentMethodModal: React.FC<DeletePaymentMethodModalProps> = ({
  paymentMethod,
  isOpen,
  onClose,
  onConfirm,
}) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Don't render if not open or no payment method
  if (!isOpen || !paymentMethod) return null;

  const handleDelete = async () => {
    setIsDeleting(true);
    setError(null);

    logger.info('Payment method deletion initiated', {
      methodId: paymentMethod.id,
      last4: paymentMethod.last4,
    });

    try {
      await onConfirm();
      logger.info('Payment method deletion successful', {
        methodId: paymentMethod.id
      });
      onClose(); // Close modal on success
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to delete payment method';
      logger.error('Payment method deletion failed', err as Error, {
        methodId: paymentMethod.id
      });
      setError(errorMessage);
      setIsDeleting(false);
    }
  };

  const handleClose = () => {
    if (!isDeleting) {
      setError(null);
      onClose();
    }
  };

  // Format card display
  const cardDisplay = `${paymentMethod.brand.charAt(0).toUpperCase() + paymentMethod.brand.slice(1)} ending in ${paymentMethod.last4}`;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Remove Payment Method"
      size="sm"
    >
      <div className="p-6">
        {/* Warning Icon */}
        <div className="flex justify-center mb-4">
          <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
            <AlertTriangle className="w-6 h-6 text-red-600" />
          </div>
        </div>

        {/* Card Details */}
        <div className="text-center mb-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Remove Payment Method?
          </h3>
          <div className="flex items-center justify-center gap-2 mb-3">
            <CreditCard className="w-5 h-5 text-gray-400" />
            <span className="text-gray-700 font-medium">{cardDisplay}</span>
          </div>
          {paymentMethod.is_default && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-3">
              <p className="text-sm text-amber-800">
                This is your default payment method. You&apos;ll need to set another card as default after removing this one.
              </p>
            </div>
          )}
          <p className="text-sm text-gray-600">
            Are you sure you want to remove this payment method? This action cannot be undone.
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleClose}
            disabled={isDeleting}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isDeleting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Removing...
              </>
            ) : (
              'Remove Card'
            )}
          </button>
        </div>
      </div>
    </Modal>
  );
};

export default DeletePaymentMethodModal;
