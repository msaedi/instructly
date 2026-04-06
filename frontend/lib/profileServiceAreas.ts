import type { ServiceAreaNeighborhood } from '@/types/instructor';

type ServiceAreaSource = {
  service_area_summary?: string | null;
  service_area_boroughs?: string[] | null;
  service_area_neighborhoods?: ServiceAreaNeighborhood[] | null;
};

function deriveBoroughsFromNeighborhoods(
  neighborhoods: ServiceAreaNeighborhood[] | null | undefined,
): string[] {
  if (!neighborhoods) return [];
  return Array.from(
    new Set(
      neighborhoods
        .map((neighborhood) => neighborhood.borough.trim())
        .filter((borough) => borough.length > 0),
    ),
  );
}

export function getServiceAreaBoroughs(source?: ServiceAreaSource | null): string[] {
  if (!source) return [];
  if (source.service_area_boroughs && source.service_area_boroughs.length > 0) {
    const normalized = source.service_area_boroughs
      .map((value) => value.trim())
      .filter((value) => value.length > 0);
    return Array.from(new Set(normalized));
  }

  return deriveBoroughsFromNeighborhoods(source.service_area_neighborhoods);
}

export function getServiceAreaDisplay(source?: ServiceAreaSource | null): string {
  if (!source) return '';
  const summary = (source.service_area_summary ?? '').trim();
  if (summary.length > 0) {
    return summary;
  }

  const boroughs = getServiceAreaBoroughs(source);
  if (boroughs.length > 0) {
    return boroughs.join(', ');
  }

  const neighborhoodBoroughs = Array.from(
    new Set(
      (source.service_area_neighborhoods || [])
        .map((n) => n.borough.trim())
        .filter((borough) => borough.length > 0),
    ),
  );

  if (neighborhoodBoroughs.length > 0) {
    return neighborhoodBoroughs.join(', ');
  }

  return '';
}
