import type { MutableRefObject } from 'react';
import type { fetchWithAuth as fetchWithAuthType } from '@/lib/api';

export type FetchWithAuthFn = typeof fetchWithAuthType;

export type ServiceAreaSubmitOptions = {
  fetcher: FetchWithAuthFn;
  payload: { neighborhood_ids: string[] };
  inFlightRef: MutableRefObject<boolean>;
  setSaving: (value: boolean) => void;
};

export async function submitServiceAreasOnce({
  fetcher,
  payload,
  inFlightRef,
  setSaving,
}: ServiceAreaSubmitOptions): Promise<void> {
  if (inFlightRef.current) return;
  inFlightRef.current = true;
  setSaving(true);
  try {
    await fetcher('/api/addresses/service-areas/me', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } finally {
    setSaving(false);
    inFlightRef.current = false;
  }
}
