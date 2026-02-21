/**
 * Formatting utilities for video session stats (duration, join times).
 * Used by LessonEnded, student detail page, and instructor detail page.
 */

export function formatSessionDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

export function formatSessionTime(iso: string | null | undefined): string {
  if (!iso) return '--';
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '--';
  }
}
