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
  const boroughs = new Set<string>();
  neighborhoods.forEach((neighborhood) => {
    const borough = neighborhood?.borough;
    if (typeof borough === 'string' && borough.trim().length > 0) {
      boroughs.add(borough.trim());
    }
  });
  return Array.from(boroughs.values());
}

export function getServiceAreaBoroughs(source: ServiceAreaSource): string[] {
  if (source.service_area_boroughs && source.service_area_boroughs.length > 0) {
    return source.service_area_boroughs
      .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
      .map((value) => value.trim());
  }

  return deriveBoroughsFromNeighborhoods(source.service_area_neighborhoods);
}

export function getServiceAreaDisplay(source: ServiceAreaSource): string {
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
        .map((n) => (typeof n.borough === 'string' ? n.borough.trim() : ''))
        .filter((borough) => borough.length > 0),
    ),
  );

  if (neighborhoodBoroughs.length > 0) {
    return neighborhoodBoroughs.join(', ');
  }

  return '';
}
