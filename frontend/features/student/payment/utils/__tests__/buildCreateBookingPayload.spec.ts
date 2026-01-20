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
        location: '123 Main St',
        metadata: {},
      },
    });

    expect(payload.start_time).toBe('09:30');
    expect(payload.end_time).toBe('10:15');
    expect(payload.selected_duration).toBe(45);
    expect(payload.location_type).toBe('student_location');
  });

  it('prefers metadata location_type over modality', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-6',
      serviceId: 'svc-6',
      bookingDate: '2025-10-10',
      booking: {
        ...baseBooking,
        location: 'Central Park',
        metadata: {
          modality: 'in_person',
          location_type: 'neutral_location',
        },
      },
    });

    expect(payload.location_type).toBe('neutral_location');
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

  it('prefers booking.address over metadata location fields', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-1',
      serviceId: 'svc-1',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: '123 Main St, Brooklyn, NY',
        metadata: {
          modality: 'in_person',
          location_address: 'Different address',
          location_lat: 41.0,
          location_lng: -74.0,
          location_place_id: 'place_meta',
        },
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
  });

  it('uses metadata address when booking.address is missing', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-2',
      serviceId: 'svc-2',
      bookingDate: '2025-02-01',
      booking: {
        ...baseBooking,
        location: 'Studio 8',
        metadata: {
          modality: 'in_person',
          location_address: 'Studio 8',
          location_lat: 40.7,
          location_lng: '-73.9',
          location_place_id: 'place_meta',
        },
      },
    });

    expect(payload.location_address).toBe('Studio 8');
    expect(payload.location_lat).toBe(40.7);
    expect(payload.location_lng).toBe(-73.9);
    expect(payload.location_place_id).toBe('place_meta');
  });

  it('parses string duration and metadata location details', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-2',
      serviceId: 'svc-2',
      bookingDate: new Date('2025-02-01T00:00:00Z'),
      booking: {
        ...baseBooking,
        duration: '90' as unknown as number,
        location: 'Studio 8',
        metadata: {
          modality: 'studio',
          location_address: 'Studio 8',
          location_lat: 40.7,
          location_lng: '-73.9',
          location_place_id: 'place_meta',
          timezone: 'America/Chicago',
        },
      },
    });

    expect(payload.selected_duration).toBe(90);
    expect(payload.location_type).toBe('instructor_location');
    expect(payload.location_address).toBe('Studio 8');
    expect(payload.location_lat).toBe(40.7);
    expect(payload.location_lng).toBe(-73.9);
    expect(payload.location_place_id).toBe('place_meta');
    expect(payload.meeting_location).toBe('Studio 8');
    expect(payload.timezone).toBe('America/Chicago');
  });

  it('derives duration from start and end times when missing', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-3',
      serviceId: 'svc-3',
      bookingDate: '2025-06-10',
      booking: {
        ...baseBooking,
        duration: 0,
        startTime: '8:15am',
        endTime: '9:45am',
        location: 'Central Park',
        metadata: { modality: 'public' },
      },
    });

    expect(payload.selected_duration).toBe(90);
    expect(payload.location_type).toBe('neutral_location');
    expect(payload.meeting_location).toBe('Central Park');
  });

  it('falls back to online when the location hint is online', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-4',
      serviceId: 'svc-4',
      bookingDate: '2025-08-01',
      booking: {
        ...baseBooking,
        location: 'Online session',
        metadata: {},
      },
    });

    expect(payload.location_type).toBe('online');
    expect(payload).not.toHaveProperty('location_address');
  });

  it('throws when booking start or end time is missing', () => {
    expect(() =>
      buildCreateBookingPayload({
        instructorId: 'inst-5',
        serviceId: 'svc-5',
        bookingDate: '2025-09-01',
        booking: {
          ...baseBooking,
          startTime: '',
        },
      }),
    ).toThrow('Booking start and end times are required to build payload');
  });
});
