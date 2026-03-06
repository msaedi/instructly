import { logger } from '@/lib/logger';

export const getDeleteConfirmationError = (confirmText: string): string =>
  confirmText === 'DELETE' ? '' : 'Please type DELETE to confirm';

export const applyDeleteConfirmationFailure = ({
  confirmText,
  setError,
}: {
  confirmText: string;
  setError: (value: string) => void;
}): boolean => {
  const confirmationError = getDeleteConfirmationError(confirmText);
  if (!confirmationError) {
    return false;
  }
  logger.warn('Delete profile attempted without proper confirmation');
  setError(confirmationError);
  return true;
};
