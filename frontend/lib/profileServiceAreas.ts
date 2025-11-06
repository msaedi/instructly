import type { ServiceAreaNeighborhood } from '@/types/instructor';

type ServiceAreaSource = {
  service_area_summary?: string | null;
  service_area_boroughs?: (string | { name?: string | null; label?: string | null })[] | null;
  service_area_neighborhoods?: ServiceAreaNeighborhood[] | null;
};

function deriveBoroughsFromNeighborhoods(
  neighborhoods: ServiceAreaNeighborhood[] | null | undefined,
): string[] {
  if (!neighborhoods) return [];
  const boroughs = new Set<string>();
  neighborhoods.forEach((neighborhood) => {
    const rawBorough = neighborhood?.borough as unknown;
    let boroughName = '';
    if (typeof rawBorough === 'string') {
      boroughName = rawBorough.trim();
    } else if (rawBorough && typeof rawBorough === 'object') {
      const label = typeof (rawBorough as { label?: string }).label === 'string'
        ? (rawBorough as { label?: string }).label?.trim()
        : undefined;
      const name = typeof (rawBorough as { name?: string }).name === 'string'
        ? (rawBorough as { name?: string }).name?.trim()
        : undefined;
      boroughName = label || name || '';
    }

    if (boroughName.length > 0) {
      boroughs.add(boroughName);
    }
  });
  return Array.from(boroughs.values());
}

export function getServiceAreaBoroughs(source: ServiceAreaSource): string[] {
  if (source.service_area_boroughs && source.service_area_boroughs.length > 0) {
    return source.service_area_boroughs
      .map((value) => {
        if (typeof value === 'string') return value.trim();
        if (value && typeof value === 'object') {
          const label = typeof value.label === 'string' ? value.label.trim() : undefined;
          const name = typeof value.name === 'string' ? value.name.trim() : undefined;
          return label || name || '';
        }
        return '';
      })
      .filter((value) => value.length > 0);
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
        .map((n) => {
          const raw = n.borough as unknown;
          if (typeof raw === 'string') return raw.trim();
          if (raw && typeof raw === 'object') {
            const label = typeof (raw as { label?: string }).label === 'string'
              ? (raw as { label?: string }).label?.trim()
              : undefined;
            const name = typeof (raw as { name?: string }).name === 'string'
              ? (raw as { name?: string }).name?.trim()
              : undefined;
            return label || name || '';
          }
          return '';
        })
        .filter((borough) => borough.length > 0),
    ),
  );

  if (neighborhoodBoroughs.length > 0) {
    return neighborhoodBoroughs.join(', ');
  }

  return '';
}
