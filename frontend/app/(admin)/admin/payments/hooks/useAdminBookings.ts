import { useQuery } from '@tanstack/react-query';

import type {
  AdminBookingDetailResponse,
  AdminBookingListItem,
  ListAdminBookingsApiV1AdminBookingsGetParams,
} from '@/src/api/generated/instructly.schemas';
import { listAdminBookingsApiV1AdminBookingsGet } from '@/src/api/generated/admin-bookings/admin-bookings';
import { PAYMENT_STATUS, type PaymentStatus } from '@/features/shared/types/paymentStatus';
export type { PaymentStatus };

export type BookingStatus = 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';

export interface BookingPerson {
  id: string;
  name: string;
  email: string;
}

export interface BookingTimelineEvent {
  timestamp: string;
  event: string;
  amount?: number;
}

export interface AdminBooking {
  id: string;
  student: BookingPerson;
  instructor: BookingPerson;
  service_name: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  total_price: number;
  status: BookingStatus;
  payment_status: PaymentStatus;
  payment_intent_id: string;
  created_at?: string;
  duration_minutes?: number;
  location_type?: string;
  meeting_location?: string;
  student_note?: string;
  instructor_note?: string;
  lesson_price?: number;
  platform_fee?: number;
  credits_applied?: number;
  instructor_payout?: number;
  platform_revenue?: number;
  timeline?: BookingTimelineEvent[];
  needs_action?: boolean;
  disputed?: boolean;
}

export interface BookingFiltersState {
  search: string;
  status: 'all' | BookingStatus;
  payment_status: 'all' | PaymentStatus;
  date_range: 'last_7_days' | 'last_30_days' | 'last_90_days' | 'all';
  quick_filter: 'all' | 'needs_action' | 'disputed' | 'settled';
  page: number;
  per_page: number;
}

export interface AdminBookingsResponse {
  bookings: AdminBooking[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export const bookingStatusOptions: { value: BookingFiltersState['status']; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'CONFIRMED', label: 'Confirmed' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'NO_SHOW', label: 'No-show' },
];

export const paymentStatusOptions: { value: BookingFiltersState['payment_status']; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: PAYMENT_STATUS.SCHEDULED, label: 'Scheduled' },
  { value: PAYMENT_STATUS.AUTHORIZED, label: 'Authorized' },
  { value: PAYMENT_STATUS.PAYMENT_METHOD_REQUIRED, label: 'Payment required' },
  { value: PAYMENT_STATUS.MANUAL_REVIEW, label: 'Manual review' },
  { value: PAYMENT_STATUS.LOCKED, label: 'Locked' },
  { value: PAYMENT_STATUS.SETTLED, label: 'Settled' },
];

export const dateRangeOptions: { value: BookingFiltersState['date_range']; label: string }[] = [
  { value: 'last_7_days', label: 'Last 7 days' },
  { value: 'last_30_days', label: 'Last 30 days' },
  { value: 'last_90_days', label: 'Last 90 days' },
  { value: 'all', label: 'All time' },
];

const PAYMENT_STATUS_VALUES: PaymentStatus[] = [
  PAYMENT_STATUS.SCHEDULED,
  PAYMENT_STATUS.AUTHORIZED,
  PAYMENT_STATUS.PAYMENT_METHOD_REQUIRED,
  PAYMENT_STATUS.MANUAL_REVIEW,
  PAYMENT_STATUS.LOCKED,
  PAYMENT_STATUS.SETTLED,
];

const BOOKING_STATUS_VALUES: BookingStatus[] = [
  'CONFIRMED',
  'COMPLETED',
  'CANCELLED',
  'NO_SHOW',
];

const toDateParam = (value: Date) => value.toISOString().slice(0, 10);

const resolveDateRange = (range: BookingFiltersState['date_range']) => {
  if (range === 'all') {
    return { dateFrom: null, dateTo: null };
  }
  const now = new Date();
  const days = range === 'last_7_days' ? 7 : range === 'last_30_days' ? 30 : 90;
  const start = new Date(now);
  start.setDate(now.getDate() - days);
  return { dateFrom: toDateParam(start), dateTo: toDateParam(now) };
};

const normalizePaymentStatus = (value?: string | null): PaymentStatus => {
  if (!value) {
    return PAYMENT_STATUS.SCHEDULED;
  }
  const lowered = value.toLowerCase();
  return PAYMENT_STATUS_VALUES.includes(lowered as PaymentStatus)
    ? (lowered as PaymentStatus)
    : PAYMENT_STATUS.SCHEDULED;
};

const normalizeBookingStatus = (value?: string | null): BookingStatus => {
  if (!value) {
    return 'CONFIRMED';
  }
  const upper = value.toUpperCase();
  return BOOKING_STATUS_VALUES.includes(upper as BookingStatus)
    ? (upper as BookingStatus)
    : 'CONFIRMED';
};

const computeNeedsAction = (bookingDate: string, endTime: string, status: BookingStatus) => {
  if (status !== 'CONFIRMED') {
    return false;
  }
  const dateTime = new Date(`${bookingDate}T${endTime}`);
  if (Number.isNaN(dateTime.getTime())) {
    return false;
  }
  return dateTime.getTime() <= Date.now();
};

export const mapBookingListItemToAdminBooking = (item: AdminBookingListItem): AdminBooking => {
  const status = normalizeBookingStatus(item.status);
  const paymentStatus = normalizePaymentStatus(item.payment_status);
  const booking: AdminBooking = {
    id: item.id,
    student: item.student,
    instructor: item.instructor,
    service_name: item.service_name,
    booking_date: item.booking_date,
    start_time: item.start_time,
    end_time: item.end_time,
    total_price: item.total_price,
    status,
    payment_status: paymentStatus,
    payment_intent_id: item.payment_intent_id ?? '',
    needs_action: computeNeedsAction(item.booking_date, item.end_time, status),
    disputed: false,
  };
  if (item.created_at) {
    booking.created_at = item.created_at;
  }
  return booking;
};

export const mapBookingDetailToAdminBooking = (
  detail: AdminBookingDetailResponse
): AdminBooking => {
  const status = normalizeBookingStatus(detail.status);
  const paymentStatus = normalizePaymentStatus(detail.payment.payment_status);
  const timeline: BookingTimelineEvent[] = detail.timeline.map((event) => {
    const timelineEvent: BookingTimelineEvent = {
      timestamp: event.timestamp,
      event: event.event,
    };
    if (event.amount !== null && event.amount !== undefined) {
      timelineEvent.amount = event.amount;
    }
    return timelineEvent;
  });

  const booking: AdminBooking = {
    id: detail.id,
    student: detail.student,
    instructor: detail.instructor,
    service_name: detail.service.name,
    booking_date: detail.booking_date,
    start_time: detail.start_time,
    end_time: detail.end_time,
    total_price: detail.payment.total_price,
    status,
    payment_status: paymentStatus,
    payment_intent_id: detail.payment.payment_intent_id ?? '',
    duration_minutes: detail.service.duration_minutes,
    lesson_price: detail.payment.lesson_price,
    platform_fee: detail.payment.platform_fee,
    credits_applied: detail.payment.credits_applied,
    instructor_payout: detail.payment.instructor_payout,
    platform_revenue: detail.payment.platform_revenue,
    timeline,
    needs_action: computeNeedsAction(detail.booking_date, detail.end_time, status),
    disputed: false,
  };
  if (detail.created_at) {
    booking.created_at = detail.created_at;
  }
  if (detail.location_type) {
    booking.location_type = detail.location_type;
  }
  if (detail.meeting_location) {
    booking.meeting_location = detail.meeting_location;
  }
  if (detail.student_note) {
    booking.student_note = detail.student_note;
  }
  if (detail.instructor_note) {
    booking.instructor_note = detail.instructor_note;
  }
  return booking;
};

const buildBookingQueryParams = (
  filters: BookingFiltersState
): ListAdminBookingsApiV1AdminBookingsGetParams => {
  const params: ListAdminBookingsApiV1AdminBookingsGetParams = {
    page: filters.page,
    per_page: filters.per_page,
  };

  const search = filters.search.trim();
  if (search) {
    params.search = search;
  }

  if (filters.status !== 'all') {
    params.status = [filters.status];
  }

  if (filters.quick_filter === 'settled') {
    params.payment_status = [PAYMENT_STATUS.SETTLED];
  } else if (filters.payment_status !== 'all') {
    params.payment_status = [filters.payment_status];
  }

  if (filters.quick_filter === 'needs_action') {
    params.needs_action = true;
  }

  const { dateFrom, dateTo } = resolveDateRange(filters.date_range);
  if (dateFrom) {
    params.date_from = dateFrom;
  }
  if (dateTo) {
    params.date_to = dateTo;
  }

  return params;
};

export function useAdminBookings(filters: BookingFiltersState) {
  return useQuery({
    queryKey: ['admin-payments', 'bookings', filters],
    queryFn: async (): Promise<AdminBookingsResponse> => {
      const params = buildBookingQueryParams(filters);
      const response = await listAdminBookingsApiV1AdminBookingsGet(params);
      let bookings = response.bookings.map(mapBookingListItemToAdminBooking);
      let total = response.total;
      let totalPages = response.total_pages;

      if (filters.quick_filter === 'disputed') {
        bookings = bookings.filter((booking) => booking.disputed);
        total = bookings.length;
        totalPages = Math.max(1, Math.ceil(total / filters.per_page));
      }

      return {
        bookings,
        total,
        page: response.page,
        per_page: response.per_page,
        total_pages: totalPages,
      };
    },
  });
}
