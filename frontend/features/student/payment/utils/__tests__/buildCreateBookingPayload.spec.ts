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

  it('throws when duration is zero and start/end produce a non-positive diff', () => {
    // endTime is before startTime, so diff is negative => cannot determine duration
    expect(() =>
      buildCreateBookingPayload({
        instructorId: 'inst-dur',
        serviceId: 'svc-dur',
        bookingDate: '2025-05-06',
        booking: {
          ...baseBooking,
          duration: 0,
          startTime: '3:00pm',
          endTime: '2:00pm', // end before start
          metadata: {},
        },
      }),
    ).toThrow('Unable to determine selected duration for booking payload');
  });

  it('throws when duration is NaN string and times are equal', () => {
    expect(() =>
      buildCreateBookingPayload({
        instructorId: 'inst-dur2',
        serviceId: 'svc-dur2',
        bookingDate: '2025-05-06',
        booking: {
          ...baseBooking,
          duration: 'abc' as unknown as number,
          startTime: '10:00',
          endTime: '10:00', // same as start
          metadata: {},
        },
      }),
    ).toThrow('Unable to determine selected duration for booking payload');
  });

  it('normalizes location_type "home" to student_location via fallback', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-home',
      serviceId: 'svc-home',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: 'My home address',
        metadata: {},
      },
    });

    expect(payload.location_type).toBe('student_location');
  });

  it('normalizes location_type "virtual" to online', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-virt',
      serviceId: 'svc-virt',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: 'Virtual meeting room',
        metadata: {},
      },
    });

    expect(payload.location_type).toBe('online');
  });

  it('falls back to student_location when normalizeHint returns null for unrecognized strings', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-unk',
      serviceId: 'svc-unk',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: 'Somewhere random',
        metadata: {
          modality: 'unknown-modality',
          location_type: 'unrecognized-location',
        },
      },
    });

    expect(payload.location_type).toBe('student_location');
  });

  it('normalizeHint returns null for whitespace-only strings', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-ws',
      serviceId: 'svc-ws',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: '   ',
        metadata: {
          modality: '   ',
          location_type: '   ',
        },
      },
    });

    // All hints are whitespace-only, so normalizeHint returns null for each
    // Falls back to default 'student_location'
    expect(payload.location_type).toBe('student_location');
    // booking.location is '   ' (whitespace) which is truthy, so fallbackLocation = '   '
    // meetingLocation = locationAddress ?? fallbackLocation ?? ...
    // locationAddress = booking.location = '   ', so meeting_location = '   '
    expect(payload.meeting_location).toBe('   ');
  });

  it('normalizeHint handles non-string values (number, boolean)', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-nonstr',
      serviceId: 'svc-nonstr',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: 'Park',
        metadata: {
          modality: 42 as unknown as string,
          location_type: true as unknown as string,
        },
      },
    });

    // Non-string values cause normalizeHint to return null
    // Fallback to booking.location which is 'Park' => not a recognized keyword => student_location
    expect(payload.location_type).toBe('student_location');
  });

  it('normalizes "in-person" modality to student_location', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-ip',
      serviceId: 'svc-ip',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: 'Some place',
        metadata: {
          modality: 'in-person',
        },
      },
    });

    expect(payload.location_type).toBe('student_location');
  });

  it('omits location_address, lat, lng, placeId for online bookings', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-online',
      serviceId: 'svc-online',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: 'Online session',
        metadata: { modality: 'remote' },
        address: {
          fullAddress: '123 Should Be Ignored',
          lat: 40.0,
          lng: -73.0,
          placeId: 'place_ignored',
        },
      },
    });

    expect(payload.location_type).toBe('online');
    // location_address is undefined for online, but fallbackLocation = 'Online session' which is truthy
    // meetingLocation = locationAddress ?? fallbackLocation ?? ...
    // Since locationAddress is undefined AND fallbackLocation is 'Online session', meeting_location = 'Online session'
    expect(payload.meeting_location).toBe('Online session');
    expect(payload).not.toHaveProperty('location_address');
    expect(payload).not.toHaveProperty('location_lat');
    expect(payload).not.toHaveProperty('location_lng');
    expect(payload).not.toHaveProperty('location_place_id');
  });

  it('uses "Online" as meeting_location when booking.location is empty for online bookings', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-online2',
      serviceId: 'svc-online2',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: '',
        metadata: { modality: 'remote' },
      },
    });

    expect(payload.location_type).toBe('online');
    expect(payload.meeting_location).toBe('Online');
  });

  it('omits timezone when instructorTimezone is whitespace-only', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-tz',
      serviceId: 'svc-tz',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        metadata: { modality: 'remote' },
      },
      instructorTimezone: '   ',
    });

    expect(payload).not.toHaveProperty('timezone');
  });

  it('resolves timezone from metadata fallback chain', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-tzfb',
      serviceId: 'svc-tzfb',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        metadata: {
          modality: 'remote',
          lessonTimezone: 'America/Los_Angeles',
        },
      },
    });

    expect(payload.timezone).toBe('America/Los_Angeles');
  });

  it('resolves timezone from instructorTimezone metadata key', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-tzfb2',
      serviceId: 'svc-tzfb2',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        metadata: {
          modality: 'remote',
          instructorTimezone: 'America/Denver',
        },
      },
    });

    expect(payload.timezone).toBe('America/Denver');
  });

  it('uses metadata place_id as fallback for location_place_id', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-pid',
      serviceId: 'svc-pid',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: '456 Oak Ave',
        metadata: {
          modality: 'in_person',
          place_id: 'place_from_metadata',
        },
      },
    });

    expect(payload.location_place_id).toBe('place_from_metadata');
  });

  it('uses duration from metadata durationMinutes key when booking.duration is null', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-dm',
      serviceId: 'svc-dm',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        duration: null as unknown as number,
        metadata: {
          modality: 'remote',
          durationMinutes: 45,
        },
      },
    });

    expect(payload.selected_duration).toBe(45);
  });

  it('uses duration from metadata duration_minutes key when booking.duration is undefined', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-dm2',
      serviceId: 'svc-dm2',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        duration: undefined as unknown as number,
        metadata: {
          modality: 'remote',
          duration_minutes: 90,
        },
      },
    });

    expect(payload.selected_duration).toBe(90);
  });

  it('normalizeNumber handles string number in metadata', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-nn',
      serviceId: 'svc-nn',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: '789 Elm St',
        metadata: {
          modality: 'in_person',
          location_lat: '40.7128',
          location_lng: '-74.0060',
        },
      },
    });

    expect(payload.location_lat).toBe(40.7128);
    expect(payload.location_lng).toBe(-74.006);
  });

  it('normalizeNumber returns undefined for non-finite string', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-nf',
      serviceId: 'svc-nf',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: 'Some location',
        metadata: {
          modality: 'in_person',
          location_lat: 'not-a-number',
          location_lng: '',
        },
      },
    });

    expect(payload).not.toHaveProperty('location_lat');
    expect(payload).not.toHaveProperty('location_lng');
  });

  it('throws when endTime is missing', () => {
    expect(() =>
      buildCreateBookingPayload({
        instructorId: 'inst-no-end',
        serviceId: 'svc-no-end',
        bookingDate: '2025-09-01',
        booking: {
          ...baseBooking,
          endTime: '',
        },
      }),
    ).toThrow('Booking start and end times are required to build payload');
  });

  it('uses metadata.duration number when booking.duration is nullish', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-mdur',
      serviceId: 'svc-mdur',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        duration: undefined as unknown as number,
        metadata: {
          modality: 'remote',
          duration: 75, // numeric duration in metadata
        },
      },
    });

    expect(payload.selected_duration).toBe(75);
  });

  it('defaults metadata to empty object when booking.metadata is undefined', () => {
    const booking = { ...baseBooking };
    delete (booking as Record<string, unknown>)['metadata'];

    const payload = buildCreateBookingPayload({
      instructorId: 'inst-nometa',
      serviceId: 'svc-nometa',
      bookingDate: '2025-05-06',
      booking,
    });

    // Should not throw -- metadata defaults to {}
    expect(payload.selected_duration).toBe(60);
  });

  it('uses "In-person lesson" as meeting_location fallback for non-online bookings with no location', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-noloc',
      serviceId: 'svc-noloc',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: undefined as unknown as string, // truly absent location
        metadata: {
          modality: 'in_person',
        },
      },
    });

    // locationAddress = undefined ?? undefined ?? undefined = undefined
    // fallbackLocation = undefined (typeof undefined !== 'string')
    // meetingLocation = undefined ?? undefined ?? 'In-person lesson'
    expect(payload.meeting_location).toBe('In-person lesson');
    expect(payload.location_type).toBe('student_location');
  });

  it('resolves timezone from lesson_timezone metadata key', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-ltz',
      serviceId: 'svc-ltz',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        metadata: {
          modality: 'remote',
          lesson_timezone: 'Pacific/Honolulu',
        },
      },
    });

    expect(payload.timezone).toBe('Pacific/Honolulu');
  });

  it('resolves timezone from instructor_timezone metadata key', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-itz',
      serviceId: 'svc-itz',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        metadata: {
          modality: 'remote',
          instructor_timezone: 'Europe/London',
        },
      },
    });

    expect(payload.timezone).toBe('Europe/London');
  });

  it('normalizeNumber returns undefined for non-number non-string types', () => {
    const payload = buildCreateBookingPayload({
      instructorId: 'inst-bool',
      serviceId: 'svc-bool',
      bookingDate: '2025-05-06',
      booking: {
        ...baseBooking,
        location: '123 Main',
        metadata: {
          modality: 'in_person',
          location_lat: true as unknown as number,
          location_lng: null as unknown as number,
        },
      },
    });

    // Boolean and null are not number or string -> undefined
    expect(payload).not.toHaveProperty('location_lat');
    expect(payload).not.toHaveProperty('location_lng');
  });
});
