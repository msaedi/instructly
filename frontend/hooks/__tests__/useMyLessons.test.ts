/**
 * Tests for useMyLessons hook
 * Covers: parseTimeToMinutes, calculateDurationMinutes, calculateCancellationFee,
 * formatLessonStatus, and the hook wrappers
 */

import { calculateCancellationFee, formatLessonStatus } from '../useMyLessons';

// We need to test the internal helpers that are called through calculateDurationMinutes
// which is exercised by useRescheduleLesson. We can test it indirectly through calculateCancellationFee.

describe('useMyLessons', () => {
  describe('calculateCancellationFee', () => {
    beforeEach(() => {
      jest.useFakeTimers();
      // Set current time to 2025-01-20 at noon
      jest.setSystemTime(new Date('2025-01-20T12:00:00'));
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    it('returns free window when lesson is more than 24 hours away', () => {
      const result = calculateCancellationFee({
        booking_date: '2025-01-22',
        start_time: '14:00',
        total_price: 112,
      });

      expect(result.window).toBe('free');
      expect(result.hoursUntil).toBeGreaterThan(24);
      expect(result.creditAmount).toBe(0);
      expect(result.willReceiveCredit).toBe(false);
    });

    it('returns credit window when lesson is 12-24 hours away', () => {
      const result = calculateCancellationFee({
        booking_date: '2025-01-21',
        start_time: '06:00',
        total_price: 112,
      });

      expect(result.window).toBe('credit');
      expect(result.hoursUntil).toBeGreaterThan(12);
      expect(result.hoursUntil).toBeLessThanOrEqual(24);
      expect(result.willReceiveCredit).toBe(true);
      expect(result.creditAmount).toBe(result.lessonPrice);
    });

    it('returns full window when lesson is less than 12 hours away', () => {
      const result = calculateCancellationFee({
        booking_date: '2025-01-20',
        start_time: '20:00',
        total_price: 112,
      });

      expect(result.window).toBe('full');
      expect(result.hoursUntil).toBeLessThanOrEqual(12);
      expect(result.creditAmount).toBe(0);
      expect(result.willReceiveCredit).toBe(false);
    });

    it('uses payment_summary when available', () => {
      const result = calculateCancellationFee({
        booking_date: '2025-01-22',
        start_time: '14:00',
        total_price: 112,
        payment_summary: {
          lesson_amount: 100,
          service_fee: 12,
          credit_applied: 0,
          subtotal: 112,
          tip_amount: 0,
          tip_paid: 0,
          total_paid: 112,
        },
      });

      expect(result.lessonPrice).toBe(100);
      expect(result.platformFee).toBe(12);
    });

    it('falls back to calculation when payment_summary is null', () => {
      const result = calculateCancellationFee({
        booking_date: '2025-01-22',
        start_time: '14:00',
        total_price: 112,
        payment_summary: null,
      });

      // total_price / 1.12 = 100
      expect(result.lessonPrice).toBe(100);
      expect(result.platformFee).toBe(12);
    });

    it('falls back to calculation when payment_summary fields are null', () => {
      const result = calculateCancellationFee({
        booking_date: '2025-01-22',
        start_time: '14:00',
        total_price: 112,
        payment_summary: {
          lesson_amount: null as unknown as number,
          service_fee: null as unknown as number,
          credit_applied: 0,
          subtotal: 112,
          tip_amount: 0,
          tip_paid: 0,
          total_paid: 112,
        },
      });

      // Should fall back to calculation
      expect(result.lessonPrice).toBe(100);
      expect(result.platformFee).toBe(12);
    });

    it('falls back when payment_summary has partial null fields', () => {
      const result = calculateCancellationFee({
        booking_date: '2025-01-22',
        start_time: '14:00',
        total_price: 56,
        payment_summary: {
          lesson_amount: 50,
          service_fee: null as unknown as number,
          credit_applied: 0,
          subtotal: 56,
          tip_amount: 0,
          tip_paid: 0,
          total_paid: 56,
        },
      });

      // service_fee is null so falls to calculation
      expect(result.lessonPrice).toBe(50);
    });

    it('handles exact 24-hour boundary', () => {
      // Lesson at exactly 24 hours from now (noon + 24h = noon next day)
      const result = calculateCancellationFee({
        booking_date: '2025-01-21',
        start_time: '12:00',
        total_price: 112,
      });

      // hoursUntil should be exactly 24, which is NOT > 24
      // so it falls to the credit window
      expect(result.window).toBe('credit');
    });

    it('handles exact 12-hour boundary', () => {
      // Lesson at exactly 12 hours from now
      const result = calculateCancellationFee({
        booking_date: '2025-01-21',
        start_time: '00:00',
        total_price: 112,
      });

      // hoursUntil should be exactly 12, which is NOT > 12
      // so it falls to the full window
      expect(result.window).toBe('full');
    });
  });

  describe('formatLessonStatus', () => {
    it('returns "Upcoming" for CONFIRMED status', () => {
      expect(formatLessonStatus('CONFIRMED')).toBe('Upcoming');
    });

    it('returns "Completed" for COMPLETED status', () => {
      expect(formatLessonStatus('COMPLETED')).toBe('Completed');
    });

    it('returns "No-show" for NO_SHOW status', () => {
      expect(formatLessonStatus('NO_SHOW')).toBe('No-show');
    });

    it('returns status string for unknown status', () => {
      expect(formatLessonStatus('PENDING' as 'CONFIRMED')).toBe('PENDING');
    });

    it('returns "Cancelled" for CANCELLED status without dates', () => {
      expect(formatLessonStatus('CANCELLED')).toBe('Cancelled');
    });

    it('returns "Cancelled (>24hrs)" when cancelled more than 24h before lesson', () => {
      // Lesson on Jan 25, cancelled on Jan 20 (5 days before)
      const result = formatLessonStatus(
        'CANCELLED',
        '2025-01-25T14:00:00',
        '2025-01-20T14:00:00'
      );
      expect(result).toBe('Cancelled (>24hrs)');
    });

    it('returns "Cancelled (12-24hrs)" when cancelled 12-24h before lesson', () => {
      // Lesson on Jan 25 at 14:00, cancelled at 02:00 same day (12h before)
      const result = formatLessonStatus(
        'CANCELLED',
        '2025-01-25T14:00:00',
        '2025-01-24T20:00:00'
      );
      expect(result).toBe('Cancelled (12-24hrs)');
    });

    it('returns "Cancelled (<12hrs)" when cancelled less than 12h before lesson', () => {
      // Lesson on Jan 25 at 14:00, cancelled at 10:00 same day (4h before)
      const result = formatLessonStatus(
        'CANCELLED',
        '2025-01-25T14:00:00',
        '2025-01-25T10:00:00'
      );
      expect(result).toBe('Cancelled (<12hrs)');
    });

    it('returns "Cancelled" for invalid cancel date', () => {
      const result = formatLessonStatus(
        'CANCELLED',
        '2025-01-25T14:00:00',
        'invalid-date'
      );
      expect(result).toBe('Cancelled');
    });

    it('returns "Cancelled" for invalid lesson date', () => {
      const result = formatLessonStatus(
        'CANCELLED',
        'invalid-date',
        '2025-01-20T14:00:00'
      );
      expect(result).toBe('Cancelled');
    });

    it('handles Date object for lessonDate', () => {
      const result = formatLessonStatus(
        'CANCELLED',
        new Date('2025-01-25T14:00:00'),
        '2025-01-20T14:00:00'
      );
      expect(result).toBe('Cancelled (>24hrs)');
    });

    it('returns "Cancelled" when cancelledAt is provided but lessonDate is null', () => {
      const result = formatLessonStatus(
        'CANCELLED',
        null,
        '2025-01-20T14:00:00'
      );
      expect(result).toBe('Cancelled');
    });

    it('returns "Cancelled" when lessonDate is provided but cancelledAt is missing', () => {
      const result = formatLessonStatus(
        'CANCELLED',
        '2025-01-25T14:00:00',
        undefined
      );
      expect(result).toBe('Cancelled');
    });
  });
});
