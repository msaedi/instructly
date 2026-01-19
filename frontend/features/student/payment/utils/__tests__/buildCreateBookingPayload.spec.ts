import { buildCreateBookingPayload } from '../buildCreateBookingPayload';
import type { BookingPayment } from '../../types';
import { PAYMENT_STATUS } from '../../types';
import { BookingType } from '@/features/shared/types/booking';

describe('buildCreateBookingPayload', () => {
  const baseBooking: BookingPayment & { metadata?: Record<string, unknown> } = {
    bookingId: 'booking-1',
    instructorId: 'inst-1',
    instructorName: 'Lee Instructor',
    lessonType: 'Math',
    date: new Date('2025-05-06T00:00:00Z'),
    startTime: '2:00pm',
    endTime: '3:00pm',
    duration: 60,
    location: 'Online',
    basePrice: 80,
    totalAmount: 95,
    bookingType: BookingType.STANDARD,
    paymentStatus: PAYMENT_STATUS.SCHEDULED,
    metadata: {
      modality: 'remote',
    },
  };

  it('builds a payload with selected_duration and 24h times', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-1',
      serviceId: 'svc-1',
      bookingDate: '2025-05-06',
      booking: baseBooking,
      instructorTimezone: 'America/New_York',
    });

    expect(payload).toEqual(
      expect.objectContaining({
        instructor_id: 'inst-1',
        instructor_service_id: 'svc-1',
        booking_date: '2025-05-06',
        start_time: '14:00',
        end_time: '15:00',
        selected_duration: 60,
        location_type: 'online',
        meeting_location: expect.stringMatching(/online/i),
        timezone: 'America/New_York',
      })
    );
  });

  it('falls back to student location when metadata is absent', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-99',
      serviceId: 'svc-2',
      bookingDate: '2025-01-01',
      booking: {
        ...baseBooking,
        startTime: '09:30',
        duration: 45,
        location: 'Studio',
        metadata: {},
      },
    });

    expect(payload.start_time).toBe('09:30');
    expect(payload.end_time).toBe('10:15');
    expect(payload.selected_duration).toBe(45);
    expect(payload.location_type).toBe('student_location');
  });

  it('includes structured address fields when provided', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-1',
      serviceId: 'svc-1',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: '123 Main St, Brooklyn, NY',
        metadata: { modality: 'in_person' },
        address: {
          fullAddress: '123 Main St, Brooklyn, NY',
          lat: 40.6892,
          lng: -73.9857,
          placeId: 'place_123',
        },
      },
    });

    expect(payload.location_address).toBe('123 Main St, Brooklyn, NY');
    expect(payload.location_lat).toBe(40.6892);
    expect(payload.location_lng).toBe(-73.9857);
    expect(payload.location_place_id).toBe('place_123');
    expect(payload.meeting_location).toBe('123 Main St, Brooklyn, NY');
  });
});
