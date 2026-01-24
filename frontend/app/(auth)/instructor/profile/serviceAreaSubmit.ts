import type { MutableRefObject } from 'react';
import { getErrorMessage } from '@/lib/api';
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
    const res = await fetcher('/api/v1/addresses/service-areas/me', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const message = await getErrorMessage(res);
      throw new Error(typeof message === 'string' ? message : 'Failed to save service areas');
    }
  } finally {
    setSaving(false);
    inFlightRef.current = false;
  }
}
