'use client';

import { useId, useState } from 'react';
import type { FormEvent } from 'react';
import { LoaderCircle } from 'lucide-react';
import Modal from '@/components/Modal';

type Props = {
  email: string;
  onClose: () => void;
  onConfirm: () => void;
  isSubmitting?: boolean;
};

export default function DeleteAccountModal({
  email,
  onClose,
  onConfirm,
  isSubmitting = false,
}: Props) {
  const [confirmEmail, setConfirmEmail] = useState('');
  const confirmId = useId();
  const normalizedExpectedEmail = email.trim().toLowerCase();
  const normalizedTypedEmail = confirmEmail.trim().toLowerCase();
  const canSubmit =
    normalizedExpectedEmail.length > 0 &&
    normalizedTypedEmail === normalizedExpectedEmail &&
    !isSubmitting;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    onConfirm();
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Delete your account?"
      description="Confirm account deletion"
      size="sm"
      autoHeight
      closeOnBackdrop={!isSubmitting}
      closeOnEscape={!isSubmitting}
    >
      <form onSubmit={handleSubmit}>
        <div className="space-y-4 text-sm text-gray-600 dark:text-gray-300">
          <p>
            This permanently deletes your iNSTAiNSTRU instructor account. You won&apos;t be able to
            log in, accept bookings, or recover this account.
          </p>
          <p>
            Your completed bookings and reviews will be retained for financial and legal purposes.
            All personal information will be erased.
          </p>
          <p>We&apos;ll email you a confirmation once your account is deleted.</p>
        </div>

        <div className="mt-5">
          <label
            htmlFor={confirmId}
            className="mb-1 block text-sm font-medium text-gray-900 dark:text-gray-100"
          >
            Type your email to confirm
          </label>
          {/*
            autoComplete="new-password" is intentional: it is more reliable
            than "off" at defeating Chrome autofill on email-like inputs.
          */}
          <input
            id={confirmId}
            type="email"
            value={confirmEmail}
            onChange={(event) => setConfirmEmail(event.target.value)}
            autoComplete="new-password"
            className="insta-form-input w-full rounded-md px-3 py-2 text-sm"
          />
        </div>

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
            type="submit"
            disabled={!canSubmit}
            className="insta-primary-btn inline-flex cursor-pointer items-center justify-center gap-2 rounded-md bg-(--color-brand) px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#6b1fb8] focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            {isSubmitting ? 'Deleting...' : 'Delete account'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
