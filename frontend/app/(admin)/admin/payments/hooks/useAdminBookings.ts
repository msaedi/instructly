import { useQuery } from '@tanstack/react-query';

export type BookingStatus = 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
export type PaymentStatus = 'pending' | 'authorized' | 'captured' | 'refunded' | 'failed';

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
  created_at: string;
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
  is_mock?: boolean;
}

export interface BookingFiltersState {
  search: string;
  status: 'all' | BookingStatus;
  payment_status: 'all' | PaymentStatus;
  date_range: 'last_7_days' | 'last_30_days' | 'last_90_days' | 'all';
  quick_filter: 'all' | 'needs_action' | 'disputed' | 'refunded';
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
  { value: 'pending', label: 'Pending' },
  { value: 'authorized', label: 'Authorized' },
  { value: 'captured', label: 'Captured' },
  { value: 'refunded', label: 'Refunded' },
  { value: 'failed', label: 'Failed' },
];

export const dateRangeOptions: { value: BookingFiltersState['date_range']; label: string }[] = [
  { value: 'last_7_days', label: 'Last 7 days' },
  { value: 'last_30_days', label: 'Last 30 days' },
  { value: 'last_90_days', label: 'Last 90 days' },
  { value: 'all', label: 'All time' },
];

const MOCK_BOOKINGS: AdminBooking[] = [
  {
    id: 'bk_01HQXYZ123ABC',
    student: { id: 'stu_01', name: 'Emma Johnson', email: 'emma@example.com' },
    instructor: { id: 'ins_01', name: 'Sarah Chen', email: 'sarah@instainstru.com' },
    service_name: 'Piano Lesson',
    booking_date: '2025-12-24',
    start_time: '14:30',
    end_time: '15:30',
    total_price: 134.4,
    status: 'CONFIRMED',
    payment_status: 'authorized',
    payment_intent_id: 'pi_3PxYz',
    created_at: '2025-12-20T10:30:00Z',
    duration_minutes: 60,
    location_type: 'Student home',
    meeting_location: '123 Main St, Brooklyn, NY',
    lesson_price: 120,
    platform_fee: 14.4,
    credits_applied: 0,
    instructor_payout: 105.6,
    platform_revenue: 28.8,
    needs_action: true,
    disputed: false,
    is_mock: true,
    timeline: [
      { timestamp: '2025-12-20T10:30:00Z', event: 'booking_created' },
      { timestamp: '2025-12-23T14:30:00Z', event: 'payment_authorized', amount: 134.4 },
    ],
  },
  {
    id: 'bk_01HQDEF456JKL',
    student: { id: 'stu_02', name: 'John Smith', email: 'john@example.com' },
    instructor: { id: 'ins_02', name: 'Mike Roberts', email: 'mike@instainstru.com' },
    service_name: 'Guitar Lesson',
    booking_date: '2025-12-23',
    start_time: '11:00',
    end_time: '12:00',
    total_price: 90,
    status: 'COMPLETED',
    payment_status: 'captured',
    payment_intent_id: 'pi_3PxYz2',
    created_at: '2025-12-18T15:20:00Z',
    duration_minutes: 60,
    location_type: 'Instructor studio',
    meeting_location: '45 Orchard St, Manhattan, NY',
    lesson_price: 80,
    platform_fee: 10,
    credits_applied: 0,
    instructor_payout: 70,
    platform_revenue: 20,
    needs_action: false,
    disputed: false,
    is_mock: true,
    timeline: [
      { timestamp: '2025-12-18T15:20:00Z', event: 'booking_created' },
      { timestamp: '2025-12-23T11:00:00Z', event: 'lesson_started' },
      { timestamp: '2025-12-23T12:00:00Z', event: 'lesson_completed' },
      { timestamp: '2025-12-24T11:00:00Z', event: 'payment_captured', amount: 90 },
    ],
  },
  {
    id: 'bk_01HQGHI789MNO',
    student: { id: 'stu_03', name: 'Lisa Park', email: 'lisa@example.com' },
    instructor: { id: 'ins_01', name: 'Sarah Chen', email: 'sarah@instainstru.com' },
    service_name: 'Piano Lesson',
    booking_date: '2025-12-22',
    start_time: '09:00',
    end_time: '10:00',
    total_price: 120,
    status: 'NO_SHOW',
    payment_status: 'refunded',
    payment_intent_id: 'pi_3PxYz3',
    created_at: '2025-12-17T09:15:00Z',
    duration_minutes: 60,
    location_type: 'Student home',
    meeting_location: '18 Union Ave, Brooklyn, NY',
    lesson_price: 110,
    platform_fee: 10,
    credits_applied: 0,
    instructor_payout: 95,
    platform_revenue: 25,
    needs_action: false,
    disputed: false,
    is_mock: true,
    timeline: [
      { timestamp: '2025-12-17T09:15:00Z', event: 'booking_created' },
      { timestamp: '2025-12-22T10:00:00Z', event: 'lesson_no_show' },
      { timestamp: '2025-12-22T12:00:00Z', event: 'refund_issued', amount: 120 },
    ],
  },
  {
    id: 'bk_01HQJKL012PQR',
    student: { id: 'stu_04', name: 'Ana Ruiz', email: 'ana@example.com' },
    instructor: { id: 'ins_03', name: 'Priya Das', email: 'priya@instainstru.com' },
    service_name: 'Violin Lesson',
    booking_date: '2025-12-20',
    start_time: '16:00',
    end_time: '17:00',
    total_price: 150,
    status: 'CANCELLED',
    payment_status: 'refunded',
    payment_intent_id: 'pi_3PxYz4',
    created_at: '2025-12-12T13:05:00Z',
    duration_minutes: 60,
    location_type: 'Student home',
    meeting_location: '77 Court St, Brooklyn, NY',
    lesson_price: 135,
    platform_fee: 15,
    credits_applied: 0,
    instructor_payout: 120,
    platform_revenue: 30,
    needs_action: false,
    disputed: true,
    is_mock: true,
    timeline: [
      { timestamp: '2025-12-12T13:05:00Z', event: 'booking_created' },
      { timestamp: '2025-12-19T18:00:00Z', event: 'booking_cancelled' },
      { timestamp: '2025-12-20T09:30:00Z', event: 'refund_issued', amount: 150 },
    ],
  },
  {
    id: 'bk_01HQMNO345STU',
    student: { id: 'stu_05', name: 'David Chen', email: 'david@example.com' },
    instructor: { id: 'ins_04', name: 'Olivia Lane', email: 'olivia@instainstru.com' },
    service_name: 'Drums Session',
    booking_date: '2025-12-26',
    start_time: '13:00',
    end_time: '14:30',
    total_price: 180,
    status: 'CONFIRMED',
    payment_status: 'pending',
    payment_intent_id: 'pi_3PxYz5',
    created_at: '2025-12-21T08:45:00Z',
    duration_minutes: 90,
    location_type: 'Instructor studio',
    meeting_location: '210 5th Ave, Manhattan, NY',
    lesson_price: 160,
    platform_fee: 20,
    credits_applied: 0,
    instructor_payout: 140,
    platform_revenue: 40,
    needs_action: true,
    disputed: false,
    is_mock: true,
    timeline: [
      { timestamp: '2025-12-21T08:45:00Z', event: 'booking_created' },
    ],
  },
];

function filterByDateRange(date: Date, range: BookingFiltersState['date_range']) {
  if (range === 'all') {
    return true;
  }
  const now = new Date();
  const cutoff = new Date(now);
  const days = range === 'last_7_days' ? 7 : range === 'last_30_days' ? 30 : 90;
  cutoff.setDate(now.getDate() - days);
  return date >= cutoff;
}

function applyBookingFilters(bookings: AdminBooking[], filters: BookingFiltersState) {
  const search = filters.search.trim().toLowerCase();
  return bookings.filter((booking) => {
    if (search) {
      const haystack = [
        booking.id,
        booking.student.name,
        booking.student.email,
        booking.instructor.name,
        booking.service_name,
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(search)) {
        return false;
      }
    }

    if (filters.status !== 'all' && booking.status !== filters.status) {
      return false;
    }

    if (filters.payment_status !== 'all' && booking.payment_status !== filters.payment_status) {
      return false;
    }

    if (filters.quick_filter === 'needs_action' && !booking.needs_action) {
      return false;
    }

    if (filters.quick_filter === 'disputed' && !booking.disputed) {
      return false;
    }

    if (filters.quick_filter === 'refunded' && booking.payment_status !== 'refunded') {
      return false;
    }

    const bookingDate = new Date(`${booking.booking_date}T00:00:00`);
    if (!filterByDateRange(bookingDate, filters.date_range)) {
      return false;
    }

    return true;
  });
}

export function useAdminBookings(filters: BookingFiltersState) {
  return useQuery({
    queryKey: ['admin-payments', 'bookings', filters],
    queryFn: async (): Promise<AdminBookingsResponse> => {
      const filtered = applyBookingFilters(MOCK_BOOKINGS, filters);
      const total = filtered.length;
      const totalPages = Math.max(1, Math.ceil(total / filters.per_page));
      const start = (filters.page - 1) * filters.per_page;
      const bookings = filtered.slice(start, start + filters.per_page);
      return {
        bookings,
        total,
        page: filters.page,
        per_page: filters.per_page,
        total_pages: totalPages,
      };
    },
  });
}
