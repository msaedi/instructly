// frontend/components/Modal.tsx
import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { logger } from '@/lib/logger';

/**
 * Modal Component
 * 
 * A reusable modal component that provides consistent behavior across the application.
 * Handles accessibility features, keyboard navigation, and body scroll locking.
 * 
 * Features:
 * - Configurable sizes (sm, md, lg, xl, full)
 * - Optional close button
 * - Backdrop click to close
 * - Escape key to close
 * - Body scroll locking when open
 * - Smooth transitions
 * - ARIA attributes for accessibility
 * 
 * @component
 * @example
 * ```tsx
 * <Modal
 *   isOpen={showModal}
 *   onClose={() => setShowModal(false)}
 *   title="My Modal"
 *   size="md"
 * >
 *   <p>Modal content goes here</p>
 * </Modal>
 * ```
 */
interface ModalProps {
  /** Whether the modal is currently open */
  isOpen: boolean;
  /** Callback function when modal should close */
  onClose: () => void;
  /** Optional title displayed in the modal header */
  title?: string;
  /** The content to display inside the modal */
  children: React.ReactNode;
  /** Size preset for the modal */
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  /** Whether to show the close button in the header */
  showCloseButton?: boolean;
  /** Whether clicking the backdrop should close the modal */
  closeOnBackdrop?: boolean;
  /** Whether pressing escape key should close the modal */
  closeOnEscape?: boolean;
  /** Additional CSS classes to apply to the modal container */
  className?: string;
}

const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  showCloseButton = true,
  closeOnBackdrop = true,
  closeOnEscape = true,
  className = ''
}) => {
  // Handle escape key press
  useEffect(() => {
    if (!isOpen || !closeOnEscape) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        logger.debug('Modal closed via Escape key');
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose, closeOnEscape]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      logger.debug('Modal opened - locking body scroll');
      document.body.style.overflow = 'hidden';
    } else {
      logger.debug('Modal closed - unlocking body scroll');
      document.body.style.overflow = 'unset';
    }

    // Cleanup on unmount
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  // Don't render if not open
  if (!isOpen) return null;

  // Size presets for modal width
  const sizeClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    full: 'max-w-7xl'
  };

  /**
   * Handle backdrop click
   */
  const handleBackdropClick = () => {
    if (closeOnBackdrop) {
      logger.debug('Modal closed via backdrop click');
      onClose();
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/20 z-40 transition-opacity"
        onClick={handleBackdropClick}
        aria-hidden="true"
      />
      
      {/* Modal Container */}
      <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4">
        <div 
          className={`pointer-events-auto w-full ${sizeClasses[size]} bg-white rounded-lg shadow-xl ${className}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? 'modal-title' : undefined}
        >
          {/* Header - only render if title or close button needed */}
          {(title || showCloseButton) && (
            <div className="flex items-center justify-between p-4 border-b">
              {title && (
                <h2 id="modal-title" className="text-lg font-semibold text-gray-900">
                  {title}
                </h2>
              )}
              {showCloseButton && (
                <button
                  onClick={() => {
                    logger.debug('Modal closed via close button');
                    onClose();
                  }}
                  className="ml-auto p-1 hover:bg-gray-100 rounded-lg transition-colors"
                  aria-label="Close modal"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              )}
            </div>
          )}
          
          {/* Content with scroll handling */}
          <div className="overflow-y-auto max-h-[calc(100vh-8rem)]">
            {children}
          </div>
        </div>
      </div>
    </>
  );
};

export default Modal;