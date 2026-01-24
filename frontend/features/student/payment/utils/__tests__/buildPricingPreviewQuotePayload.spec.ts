import {
  buildPricingPreviewQuotePayload,
  buildPricingPreviewQuotePayloadBase,
} from '../buildPricingPreviewQuotePayload';

describe('buildPricingPreviewQuotePayload', () => {
  const baseBooking = {
    instructorId: 'inst-1',
    date: '2025-05-06',
    startTime: '10:00',
    duration: 60,
    location: '123 Main St',
  };

  it('maps metadata location_type when provided', () => {
    const payload = buildPricingPreviewQuotePayloadBase({
      ...baseBooking,
      instructorServiceId: 'svc-1',
      metadata: { location_type: 'instructor_location' },
      location: 'Anywhere',
    });

    expect(payload.location_type).toBe('instructor_location');
    expect(payload.instructor_service_id).toBe('svc-1');
  });

  it('uses online keywords when hint is missing', () => {
    const onlinePayload = buildPricingPreviewQuotePayloadBase({
      ...baseBooking,
      location: 'Online session',
    });
    const remotePayload = buildPricingPreviewQuotePayloadBase({
      ...baseBooking,
      location: 'Remote session',
    });
    const virtualPayload = buildPricingPreviewQuotePayloadBase({
      ...baseBooking,
      location: 'Virtual lesson',
    });

    expect(onlinePayload.location_type).toBe('online');
    expect(remotePayload.location_type).toBe('online');
    expect(virtualPayload.location_type).toBe('online');
    expect(remotePayload.instructor_service_id).toBe('');
  });

  it('defaults to student_location with no hints or keywords', () => {
    const payload = buildPricingPreviewQuotePayloadBase({
      ...baseBooking,
      serviceId: 'svc-2',
      date: new Date('2025-05-06T00:00:00Z'),
      location: '123 Main St',
    });

    expect(payload.location_type).toBe('student_location');
    expect(payload.instructor_service_id).toBe('svc-2');
  });

  it('falls back to metadata.serviceId and zero credits when omitted', () => {
    const payload = buildPricingPreviewQuotePayload({
      ...baseBooking,
      location: 'Central Park',
      metadata: {
        serviceId: 'svc-meta',
        modality: 'neutral_location',
      },
    });

    expect(payload.instructor_service_id).toBe('svc-meta');
    expect(payload.location_type).toBe('neutral_location');
    expect(payload.applied_credit_cents).toBe(0);
  });

  it('ignores unmapped hints and uses location keywords', () => {
    const payload = buildPricingPreviewQuotePayloadBase({
      ...baseBooking,
      metadata: { location_type: 'mystery_type' },
      location: 'Online lesson',
    });

    expect(payload.location_type).toBe('online');
  });
});
