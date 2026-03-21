import { buildAvailabilityCheckRequest, type AvailabilityCheckBooking } from '../buildAvailabilityCheckRequest';
import { PAYMENT_STATUS } from '../../types';
import { BookingType } from '@/features/shared/types/booking';

describe('buildAvailabilityCheckRequest', () => {
  const baseBooking: AvailabilityCheckBooking = {
    bookingId: 'booking-123',
    instructorId: 'instructor-456',
    instructorName: 'Lee Instructor',
    lessonType: 'Math',
    date: new Date('2025-06-20T00:00:00Z'),
    startTime: '3:00pm',
    endTime: '4:00pm',
    duration: 60,
    location: '123 Main St',
    basePrice: 80,
    totalAmount: 95,
    bookingType: BookingType.STANDARD,
    paymentStatus: PAYMENT_STATUS.SCHEDULED,
    metadata: {
      serviceId: 'service-789',
      location_type: 'student_location',
    },
  };

  const build = (
    overrides: Partial<AvailabilityCheckBooking> = {},
    updatedOverrides: Partial<AvailabilityCheckBooking> = {},
    baseOverrides: Partial<AvailabilityCheckBooking> = {},
  ) =>
    buildAvailabilityCheckRequest({
      bookingCandidate: { ...baseBooking, ...overrides, metadata: { ...baseBooking.metadata, ...(overrides.metadata ?? {}) } },
      updatedBookingData: { ...baseBooking, ...updatedOverrides, metadata: { ...baseBooking.metadata, ...(updatedOverrides.metadata ?? {}) } },
      bookingData: { ...baseBooking, ...baseOverrides, metadata: { ...baseBooking.metadata, ...(baseOverrides.metadata ?? {}) } },
    });

  it('builds a request from canonical booking data', () => {
    expect(build()).toEqual(
      expect.objectContaining({
        instructor_id: 'instructor-456',
        instructor_service_id: 'service-789',
        booking_date: '2025-06-20',
        start_time: '15:00',
        end_time: '16:00',
        selected_duration: 60,
        location_type: 'student_location',
        exclude_booking_id: 'booking-123',
      }),
    );
  });

  it('coerces numeric identifiers and uses fallback location and coords from older booking state', () => {
    const request = build(
      {
        instructorId: 99 as unknown as string,
        serviceId: 321 as unknown as string,
        bookingId: '   ',
        location: 'At your location',
        metadata: { serviceId: null, location_type: null },
      },
      {
        location: 'Remote lesson',
        address: { fullAddress: 'Updated Address', lat: 40.7, lng: -73.9 },
        bookingId: 'updated-booking',
        metadata: { serviceId: null, modality: 'remote' },
      },
      {
        bookingId: 'fallback-booking',
        metadata: { serviceId: null },
      },
    );

    expect(request).toEqual(
      expect.objectContaining({
        instructor_id: '99',
        instructor_service_id: '321',
        location_type: 'online',
        location_lat: 40.7,
        location_lng: -73.9,
        exclude_booking_id: 'updated-booking',
      }),
    );
  });

  it('falls back to updated booking values when the candidate is missing identifiers, time, and location details', () => {
    const request = build(
      {
        instructorId: null as unknown as string,
        serviceId: null as unknown as string,
        startTime: null as unknown as string,
        endTime: null as unknown as string,
        duration: null as unknown as number,
        location: '',
        bookingId: '',
        metadata: { serviceId: null, location_type: null, modality: null },
      },
      {
        instructorId: 88 as unknown as string,
        serviceId: 654 as unknown as string,
        startTime: '4:30pm',
        endTime: '',
        duration: 90,
        location: 'Remote session',
        bookingId: 'updated-123',
        address: {
          fullAddress: 'Remote session',
          lat: 40.8,
          lng: -73.95,
        },
        metadata: { serviceId: null, location_type: null, modality: null },
      },
      {
        duration: null as unknown as number,
        endTime: null as unknown as string,
        metadata: { serviceId: null, location_type: null, modality: null },
      },
    );

    expect(request).toEqual(
      expect.objectContaining({
        instructor_id: '88',
        instructor_service_id: '654',
        booking_date: '2025-06-20',
        start_time: '16:30',
        end_time: '18:00',
        selected_duration: 90,
        location_type: 'online',
        location_lat: 40.8,
        location_lng: -73.95,
        exclude_booking_id: 'updated-123',
      }),
    );
  });

  it('falls back to base booking values and omits coords and booking ids when none are valid', () => {
    const request = build(
      {
        instructorId: null as unknown as string,
        serviceId: null as unknown as string,
        startTime: null as unknown as string,
        endTime: null as unknown as string,
        duration: null as unknown as number,
        location: '',
        bookingId: '',
        address: {
          fullAddress: 'Candidate address',
          lat: 'bad' as unknown as number,
          lng: 'bad' as unknown as number,
        },
        metadata: { serviceId: null },
      },
      {
        instructorId: null as unknown as string,
        serviceId: null as unknown as string,
        startTime: null as unknown as string,
        endTime: null as unknown as string,
        duration: null as unknown as number,
        location: '',
        bookingId: '',
        address: {
          fullAddress: 'Updated address',
          lat: 'bad' as unknown as number,
          lng: 'bad' as unknown as number,
        },
        metadata: { serviceId: null },
      },
      {
        instructorId: 'base-instructor',
        serviceId: 'base-service',
        startTime: '7:15am',
        endTime: null as unknown as string,
        duration: 45,
        location: 'Library Plaza',
        bookingId: '   ',
        metadata: { serviceId: null },
      },
    );

    expect(request).toEqual(
      expect.objectContaining({
        instructor_id: 'base-instructor',
        instructor_service_id: 'base-service',
        booking_date: '2025-06-20',
        start_time: '07:15',
        end_time: '08:00',
        selected_duration: 45,
        location_type: 'student_location',
      }),
    );
    expect(request).not.toHaveProperty('location_lat');
    expect(request).not.toHaveProperty('location_lng');
    expect(request).not.toHaveProperty('exclude_booking_id');
  });

  it('returns null when the instructor id cannot be resolved', () => {
    expect(
      build(
        { instructorId: '' },
        { instructorId: '' },
        { instructorId: '' },
      ),
    ).toBeNull();
  });

  it('returns null when the service id cannot be resolved', () => {
    expect(
      build(
        { serviceId: null as unknown as string, metadata: { serviceId: null } },
        { serviceId: null as unknown as string, metadata: { serviceId: null } },
        { serviceId: null as unknown as string, metadata: { serviceId: null } },
      ),
    ).toBeNull();
  });

  it('returns null when the booking date is missing or invalid', () => {
    expect(
      build(
        { date: null as unknown as Date },
        { date: null as unknown as Date },
        { date: null as unknown as Date },
      ),
    ).toBeNull();
    expect(build({ date: 'not-a-date' as unknown as Date })).toBeNull();
  });

  it('returns null when the start time is missing or invalid', () => {
    expect(build({ startTime: '' })).toBeNull();
    expect(build({ startTime: 'not-a-time' })).toBeNull();
  });

  it('parses string durations and falls back to metadata duration when needed', () => {
    const stringDurationRequest = build({
      duration: '75' as unknown as number,
      endTime: 'invalid-end-time',
    });
    expect(stringDurationRequest).toEqual(
      expect.objectContaining({
        selected_duration: 75,
        end_time: '16:15',
      }),
    );

    const metadataDurationRequest = build(
      {
        duration: undefined as unknown as number,
        metadata: { serviceId: 'service-789', location_type: 'student_location' },
      },
      {
        duration: undefined as unknown as number,
        metadata: { duration_minutes: 90 },
      },
      {
        duration: undefined as unknown as number,
      },
    );
    expect(metadataDurationRequest).toEqual(
      expect.objectContaining({
        selected_duration: 90,
        end_time: '16:00',
      }),
    );
  });

  it('returns null when no usable duration exists', () => {
    expect(
      build(
        {
          duration: undefined as unknown as number,
          metadata: { serviceId: 'service-789', location_type: 'student_location' },
        },
        {
          duration: undefined as unknown as number,
          metadata: { serviceId: 'service-789', location_type: 'student_location' },
        },
        {
          duration: undefined as unknown as number,
          metadata: { serviceId: 'service-789', location_type: 'student_location' },
        },
      ),
    ).toBeNull();
  });
});
