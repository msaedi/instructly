import Link from 'next/link';
import type { ConversationBooking } from '../types';
import { formatBookingDateTime } from '../utils';
import { shortenBookingId } from '@/lib/bookingId';
import { getBookingStatusBadgeClasses } from '@/lib/bookingStatus';

export type ConversationBookingCardProps = {
  booking: ConversationBooking;
  href: string;
  status: string;
  statusLabel: string;
  variant: 'primary' | 'default' | 'completed';
};

const bookingCardVariantClasses: Record<ConversationBookingCardProps['variant'], string> = {
  primary:
    'border-[#E5D7FE] bg-(--color-brand-lavender) hover:bg-[#EEE4FE] dark:border-[#5B21B6] dark:bg-[#2A114A] dark:hover:bg-[#34145B]',
  default:
    'border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800',
  completed:
    'border-gray-200 bg-gray-100 hover:bg-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700',
};

export function ConversationBookingCard({
  booking,
  href,
  status,
  statusLabel,
  variant,
}: ConversationBookingCardProps) {
  return (
    <Link
      href={href}
      data-testid={`chat-header-booking-card-${booking.id}`}
      className={`block rounded-xl border p-3 transition-colors ${bookingCardVariantClasses[variant]}`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{booking.service_name}</p>
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${getBookingStatusBadgeClasses(status)}`}
        >
          {statusLabel}
        </span>
      </div>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {formatBookingDateTime(booking)}
      </p>
      <p className="mt-2 text-[10px] font-mono uppercase tracking-[0.18em] text-gray-400 dark:text-gray-300">
        #{shortenBookingId(booking.id)}
      </p>
    </Link>
  );
}
