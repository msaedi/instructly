// Pure booking helpers shared across features (no side-effects beyond sessionStorage helpers)

// Calculate end time given a start time (HH:MM or HH:MM:SS) and duration minutes
export function calculateEndTime(startTime: string, durationMinutes: number): string {
  if (!startTime) {
    throw new Error('Start time is required');
  }

  const parts = startTime.split(':');
  if (parts.length < 2) {
    throw new Error('Invalid time format. Expected HH:MM');
  }

  const hours = parseInt(parts[0] || '0', 10) || 0;
  const minutes = parseInt(parts[1] || '0', 10) || 0;

  const total = hours * 60 + minutes + durationMinutes;
  const endH = Math.floor(total / 60) % 24;
  const endM = total % 60;
  return `${endH.toString().padStart(2, '0')}:${endM.toString().padStart(2, '0')}`;
}

// Booking intent helpers (sessionStorage only)
export function storeBookingIntent(bookingIntent: {
  instructorId: string;
  serviceId?: string;
  date: string;
  time: string;
  duration: number;
  skipModal?: boolean;
}): void {
  try {
    sessionStorage.setItem('bookingIntent', JSON.stringify(bookingIntent));
  } catch {}
}

export function getBookingIntent(): {
  instructorId: string;
  serviceId?: string;
  date: string;
  time: string;
  duration: number;
  skipModal?: boolean;
} | null {
  try {
    const s = sessionStorage.getItem('bookingIntent');
    type StoredBookingIntent = {
      instructorId: string;
      serviceId?: string;
      date: string;
      time: string;
      duration: number;
      skipModal?: boolean;
    };
    return s ? (JSON.parse(s) as StoredBookingIntent) : null;
  } catch {
    return null;
  }
}

export function clearBookingIntent(): void {
  try {
    sessionStorage.removeItem('bookingIntent');
  } catch {}
}
