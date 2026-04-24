'use client';

import { LoaderCircle } from 'lucide-react';
import Modal from '@/components/Modal';

type ResumeAccountModalProps = {
  onClose: () => void;
  onConfirm: () => void;
  isSubmitting?: boolean;
};

export default function ResumeAccountModal({
  onClose,
  onConfirm,
  isSubmitting = false,
}: ResumeAccountModalProps) {
  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Resume your account?"
      description="Confirm account resume"
      size="sm"
      autoHeight
      closeOnBackdrop={!isSubmitting}
      closeOnEscape={!isSubmitting}
    >
      <p className="text-sm text-gray-600 dark:text-gray-300">
        You&apos;ll be visible in search and can receive new bookings again. We&apos;ll email you a
        confirmation.
      </p>
      <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={onClose}
          disabled={isSubmitting}
          className="inline-flex cursor-pointer items-center justify-center rounded-md border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 focus:outline-none dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={isSubmitting}
          className="insta-primary-btn inline-flex cursor-pointer items-center justify-center gap-2 rounded-md bg-(--color-brand) px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#6b1fb8] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
          {isSubmitting ? 'Resuming...' : 'Resume account'}
        </button>
      </div>
    </Modal>
  );
}
