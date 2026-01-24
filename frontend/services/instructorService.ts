import { fetchWithAuth, getErrorMessage } from '@/lib/api';

export type ServiceAreaCheckResponse = {
  instructor_id: string;
  is_covered: boolean;
  coordinates: {
    lat: number;
    lng: number;
  };
};

export const instructorService = {
  checkServiceArea: async (
    instructorId: string,
    lat: number,
    lng: number
  ): Promise<ServiceAreaCheckResponse> => {
    const params = new URLSearchParams({
      lat: String(lat),
      lng: String(lng),
    });
    const res = await fetchWithAuth(
      `/api/v1/instructors/${encodeURIComponent(instructorId)}/check-service-area?${params.toString()}`
    );
    if (!res.ok) {
      throw new Error(await getErrorMessage(res));
    }
    return res.json() as Promise<ServiceAreaCheckResponse>;
  },
};
