'use client';

type PausedAccountBannerProps = {
  onResume: () => void;
};

export default function PausedAccountBanner({ onResume }: PausedAccountBannerProps) {
  return (
    <div
      role="region"
      aria-label="Account paused"
      className="mb-6 rounded-md border border-purple-200 bg-purple-50 px-4 py-3 text-sm text-gray-800 dark:border-purple-700 dark:bg-purple-950/40 dark:text-gray-100"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-3xl">
          <strong className="font-semibold text-(--color-brand) dark:text-purple-200">
            Your account is paused.
          </strong>{' '}
          You&apos;re not visible in search and can&apos;t receive new bookings. Existing bookings are
          still active. Cancel them from your bookings list if needed.
        </p>
        <button
          type="button"
          onClick={onResume}
          className="inline-flex cursor-pointer items-center justify-center rounded-md px-3 py-1.5 text-sm font-semibold text-(--color-brand) transition-colors hover:bg-white/80 focus:outline-none dark:text-purple-200 dark:hover:bg-purple-900/50"
        >
          Resume account
        </button>
      </div>
    </div>
  );
}
