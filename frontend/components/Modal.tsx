// frontend/components/Modal.tsx
import React, { useEffect } from 'react';
import { X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  showCloseButton?: boolean;
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
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
  // Handle escape key
  useEffect(() => {
    if (!isOpen || !closeOnEscape) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose, closeOnEscape]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const sizeClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    full: 'max-w-7xl'
  };

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/20 z-40 transition-opacity"
        onClick={closeOnBackdrop ? onClose : undefined}
        aria-hidden="true"
      />
      
      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4">
        <div 
          className={`pointer-events-auto w-full ${sizeClasses[size]} bg-white rounded-lg shadow-xl ${className}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? 'modal-title' : undefined}
        >
          {/* Header */}
          {(title || showCloseButton) && (
            <div className="flex items-center justify-between p-4 border-b">
              {title && (
                <h2 id="modal-title" className="text-lg font-semibold text-gray-900">
                  {title}
                </h2>
              )}
              {showCloseButton && (
                <button
                  onClick={onClose}
                  className="ml-auto p-1 hover:bg-gray-100 rounded-lg transition-colors"
                  aria-label="Close modal"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              )}
            </div>
          )}
          
          {/* Content */}
          <div className="overflow-y-auto max-h-[calc(100vh-8rem)]">
            {children}
          </div>
        </div>
      </div>
    </>
  );
};

export default Modal;