// frontend/components/Modal.tsx
import React from 'react';
import { X } from 'lucide-react';
import { logger } from '@/lib/logger';
import * as Dialog from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';

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
  /** Optional description announced to assistive tech */
  description?: string;
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
  description,
  children,
  size = 'md',
  showCloseButton = true,
  closeOnBackdrop = true,
  closeOnEscape = true,
  className = '',
  noPadding = false,
  footer,
}) => {
  // Note: Radix Dialog manages focus trap, aria-hiding, and body scroll lock.

  // Size presets for modal width
  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-2xl',
    xl: 'max-w-4xl',
    full: 'max-w-7xl',
  };

  const accessibleTitle = title ?? 'Modal';
  const accessibleDescription = description ?? 'Dialog content';

  return (
    <Dialog.Root
      open={isOpen}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          logger.debug('Modal closed via onOpenChange');
          onClose();
        }
      }}
   >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40 transition-all duration-200" />
        <Dialog.Content
          className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4 sm:p-6"
          onEscapeKeyDown={(e) => {
            if (!closeOnEscape) {
              e.preventDefault();
            }
          }}
          onInteractOutside={(e) => {
            if (!closeOnBackdrop) {
              e.preventDefault();
            }
          }}
        >
          <VisuallyHidden>
            <Dialog.Title>{accessibleTitle}</Dialog.Title>
            <Dialog.Description>{accessibleDescription}</Dialog.Description>
          </VisuallyHidden>
          <div
            className={`
              pointer-events-auto w-full ${sizeClasses[size]}
              bg-white dark:bg-gray-800 rounded-xl shadow-2xl
              transform transition-all duration-200 ease-out
              relative ${className}
            `}
          >
            {title && (
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                  {title}
                </h2>
                {showCloseButton && (
                  <Dialog.Close asChild>
                    <button
                      onClick={() => logger.debug('Modal closed via close button')}
                      className={`${title ? 'ml-auto' : ''} p-0 bg-transparent cursor-pointer`}
                      aria-label="Close modal"
                    >
                      <X
                        className="w-5 h-5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
                        aria-hidden="true"
                      />
                    </button>
                  </Dialog.Close>
                )}
              </div>
            )}
            {!title && showCloseButton && (
              <Dialog.Close asChild>
                <button
                  onClick={() => logger.debug('Modal closed via floating close button')}
                  className="absolute top-3 right-3 p-0 bg-transparent cursor-pointer"
                  aria-label="Close modal"
                >
                  <X
                    className="w-5 h-5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
                    aria-hidden="true"
                  />
                </button>
              </Dialog.Close>
            )}
            <div
              className={`
                overflow-y-auto scrollbar-hide
                ${footer ? 'max-h-[calc(100vh-12rem)]' : 'max-h-[calc(100vh-8rem)]'}
                ${noPadding ? '' : 'p-6'}
              `}
            >
              {children}
            </div>
            {footer && (
              <div className="px-6 py-4 bg-gray-50 dark:bg-gray-700 border-t border-gray-200 dark:border-gray-600 rounded-b-xl">
                {footer}
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

export default Modal;
