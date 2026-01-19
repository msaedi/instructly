import {
  calculateEndTime,
  storeBookingIntent,
  getBookingIntent,
  clearBookingIntent,
} from '../booking';

describe('calculateEndTime', () => {
  it('calculates end time for a standard duration', () => {
    expect(calculateEndTime('10:00', 60)).toBe('11:00');
  });

  it('wraps around midnight when duration crosses a day boundary', () => {
    expect(calculateEndTime('23:30', 90)).toBe('01:00');
  });

  it('throws when start time is missing or invalid', () => {
    expect(() => calculateEndTime('', 30)).toThrow('Start time is required');
    expect(() => calculateEndTime('10', 30)).toThrow('Invalid time format');
  });
});

describe('booking intent helpers', () => {
  let store: Record<string, string>;
  const sessionStorageMock: jest.Mocked<Storage> = {
    getItem: jest.fn((key: string) => (key in store ? store[key] : null)),
    setItem: jest.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete store[key];
    }),
    clear: jest.fn(() => {
      store = {};
    }),
    key: jest.fn((index: number) => Object.keys(store)[index] ?? null),
    length: 0,
  } as unknown as jest.Mocked<Storage>;

  beforeEach(() => {
    store = {};
    sessionStorageMock.getItem.mockClear();
    sessionStorageMock.setItem.mockClear();
    sessionStorageMock.removeItem.mockClear();
    Object.defineProperty(window, 'sessionStorage', {
      value: sessionStorageMock,
      configurable: true,
    });
  });

  describe('storeBookingIntent', () => {
    it('serializes the booking intent into sessionStorage', () => {
      storeBookingIntent({
        instructorId: 'instructor-1',
        serviceId: 'service-1',
        date: '2025-01-01',
        time: '10:00',
        duration: 60,
      });

      expect(sessionStorageMock.setItem).toHaveBeenCalledWith(
        'bookingIntent',
        expect.any(String)
      );
      expect(store.bookingIntent).toBeDefined();
      const storedValue = store.bookingIntent as string;
      const stored = JSON.parse(storedValue) as Record<string, unknown>;
      expect(stored).toMatchObject({
        instructorId: 'instructor-1',
        serviceId: 'service-1',
        date: '2025-01-01',
        time: '10:00',
        duration: 60,
      });
    });

    it('stores optional fields when provided', () => {
      storeBookingIntent({
        instructorId: 'instructor-2',
        date: '2025-01-02',
        time: '12:00',
        duration: 45,
        skipModal: true,
      });

      expect(store.bookingIntent).toBeDefined();
      const storedValue = store.bookingIntent as string;
      const stored = JSON.parse(storedValue) as Record<string, unknown>;
      expect(stored.skipModal).toBe(true);
    });

    it('does not persist data when storage throws', () => {
      sessionStorageMock.setItem.mockImplementationOnce(() => {
        throw new Error('Quota exceeded');
      });

      storeBookingIntent({
        instructorId: 'instructor-3',
        date: '2025-01-03',
        time: '08:00',
        duration: 30,
      });

      expect(store.bookingIntent).toBeUndefined();
    });
  });

  describe('getBookingIntent', () => {
    it('returns parsed booking intent when present', () => {
      store.bookingIntent = JSON.stringify({
        instructorId: 'instructor-4',
        date: '2025-01-04',
        time: '09:00',
        duration: 90,
      });

      expect(getBookingIntent()).toMatchObject({
        instructorId: 'instructor-4',
        date: '2025-01-04',
        time: '09:00',
        duration: 90,
      });
    });

    it('returns null when no booking intent is stored', () => {
      expect(getBookingIntent()).toBeNull();
    });

    it('returns null when stored JSON is invalid', () => {
      store.bookingIntent = '{invalid-json';
      expect(getBookingIntent()).toBeNull();
    });
  });

  describe('clearBookingIntent', () => {
    it('removes the booking intent from storage', () => {
      store.bookingIntent = JSON.stringify({ instructorId: 'instructor-5', date: '2025-01-05', time: '10:00', duration: 60 });

      clearBookingIntent();

      expect(sessionStorageMock.removeItem).toHaveBeenCalledWith('bookingIntent');
      expect(getBookingIntent()).toBeNull();
    });

    it('handles clearing when no booking intent is stored', () => {
      clearBookingIntent();
      expect(sessionStorageMock.removeItem).toHaveBeenCalledWith('bookingIntent');
      expect(getBookingIntent()).toBeNull();
    });

    it('leaves data intact when removal fails', () => {
      store.bookingIntent = JSON.stringify({ instructorId: 'instructor-6', date: '2025-01-06', time: '11:00', duration: 30 });
      sessionStorageMock.removeItem.mockImplementationOnce(() => {
        throw new Error('Removal failed');
      });

      clearBookingIntent();

      expect(getBookingIntent()).toMatchObject({
        instructorId: 'instructor-6',
        date: '2025-01-06',
        time: '11:00',
        duration: 30,
      });
    });
  });
});
