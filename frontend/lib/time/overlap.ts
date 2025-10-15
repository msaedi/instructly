export function minutesSinceHHMM(hhmm24: string): number {
  const [hoursRaw = '0', minutesRaw = '0'] = String(hhmm24 ?? '').trim().split(':');
  const hours = Number.parseInt(hoursRaw, 10);
  const minutes = Number.parseInt(minutesRaw, 10);

  if (!Number.isFinite(hours) || hours < 0 || hours > 23) {
    throw new Error(`Invalid HH:MM hour value: "${hhmm24}"`);
  }
  if (!Number.isFinite(minutes) || minutes < 0 || minutes > 59) {
    throw new Error(`Invalid HH:MM minute value: "${hhmm24}"`);
  }

  return hours * 60 + minutes;
}

export function overlapsHHMM(
  aStartHHMM: string,
  aDurMin: number,
  bStartHHMM: string,
  bDurMin: number,
): boolean {
  const aStart = minutesSinceHHMM(aStartHHMM);
  const bStart = minutesSinceHHMM(bStartHHMM);
  const aEnd = aStart + aDurMin;
  const bEnd = bStart + bDurMin;

  // Backend parity: start1 < end2 && end1 > start2
  return aStart < bEnd && aEnd > bStart;
}
