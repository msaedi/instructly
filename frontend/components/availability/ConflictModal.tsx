import { X } from 'lucide-react';
import clsx from 'clsx';

interface ConflictModalProps {
  open: boolean;
  serverVersion?: string;
  onDismiss: () => void;
  onRefresh: () => Promise<void> | void;
  onOverwrite: () => Promise<void> | void;
  isRefreshing?: boolean;
  isOverwriting?: boolean;
}

export default function ConflictModal({
  open,
  serverVersion,
  onDismiss,
  onRefresh,
  onOverwrite,
  isRefreshing = false,
  isOverwriting = false,
}: ConflictModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div
        className="absolute inset-0 bg-black/30"
        aria-hidden="true"
        onClick={onDismiss}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="availability-conflict-title"
        aria-describedby="availability-conflict-desc"
        className="relative w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <button
          type="button"
          onClick={onDismiss}
          className="absolute right-3 top-3 rounded-full p-1 text-gray-500 hover:bg-gray-100"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
        <h3 id="availability-conflict-title" className="text-lg font-semibold text-gray-900">
          New changes detected
        </h3>
        <p id="availability-conflict-desc" className="mt-2 text-sm text-gray-600">
          Another session updated this week while you were editing. Refresh to keep their edits,
          or overwrite to push your current plan.
          {serverVersion && (
            <span className="mt-2 block text-xs font-mono text-gray-500">
              Latest version: {serverVersion}
            </span>
          )}
        </p>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing || isOverwriting}
            className={clsx(
              'inline-flex items-center justify-center rounded-full border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100',
              (isRefreshing || isOverwriting) && 'cursor-not-allowed opacity-60'
            )}
          >
            {isRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
          <button
            type="button"
            onClick={onOverwrite}
            disabled={isOverwriting || isRefreshing}
            className={clsx(
              'inline-flex items-center justify-center rounded-full bg-[#7E22CE] px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#6b1ebe]',
              (isOverwriting || isRefreshing) && 'cursor-not-allowed opacity-60'
            )}
          >
            {isOverwriting ? 'Overwriting…' : 'Overwrite'}
          </button>
        </div>
      </div>
    </div>
  );
}
