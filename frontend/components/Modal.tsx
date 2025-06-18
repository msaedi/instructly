// frontend/components/Modal.tsx
import React, { useEffect } from 'react';
import { X } from 'lucide-react';
import { logger } from '@/lib/logger';

/**
 * Modal Component with Enhanced Professional Design
 * 
 * A reusable modal component that provides consistent, beautiful styling across the application.
 * Now includes built-in padding, better shadows, and professional visual design.
 * 
 * @component
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
  /** Whether to apply default content padding (can be disabled for custom layouts) */
  noPadding?: boolean;
  /** Optional footer content (will be styled appropriately) */
  footer?: React.ReactNode;
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
  className = '',
  noPadding = false,
  footer
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
    sm: 'max-w-md',
    md: 'max-w-lg',
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
      {/* Enhanced Backdrop with better blur and opacity */}
      <div 
        className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40 transition-all duration-200"
        onClick={handleBackdropClick}
        aria-hidden="true"
      />
      
      {/* Modal Container with better positioning and animation */}
      <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4 sm:p-6">
        <div 
          className={`
            pointer-events-auto w-full ${sizeClasses[size]} 
            bg-white rounded-xl shadow-2xl 
            transform transition-all duration-200 ease-out
            ${className}
          `}
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? 'modal-title' : undefined}
        >
          {/* Enhanced Header */}
          {(title || showCloseButton) && (
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              {title && (
                <h2 id="modal-title" className="text-xl font-semibold text-gray-900">
                  {title}
                </h2>
              )}
              {showCloseButton && (
                <button
                  onClick={() => {
                    logger.debug('Modal closed via close button');
                    onClose();
                  }}
                  className={`
                    ${title ? 'ml-auto' : ''} 
                    p-2 hover:bg-gray-100 rounded-lg transition-colors duration-150
                    focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-400
                  `}
                  aria-label="Close modal"
                >
                  <X className="w-5 h-5 text-gray-400 hover:text-gray-600" />
                </button>
              )}
            </div>
          )}
          
          {/* Enhanced Content Area */}
          <div className={`
            overflow-y-auto 
            ${footer ? 'max-h-[calc(100vh-12rem)]' : 'max-h-[calc(100vh-8rem)]'}
            ${noPadding ? '' : 'p-6'}
          `}>
            {children}
          </div>
          
          {/* Optional Footer */}
          {footer && (
            <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 rounded-b-xl">
              {footer}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default Modal;