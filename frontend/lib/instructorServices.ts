import { publicApi } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import type { InstructorService } from '@/types/instructor';

type CatalogSummary = { id: string; name: string };

export type UIInstructorService = InstructorService & {
  name?: string | null;
  service_catalog_name?: string | null;
};

export type HydrateFn = (id: string) => string | undefined;

/** Prefer server-provided name first, then catalog fallback, finally the ULID. */
export function displayServiceName(
  svc: { service_catalog_id?: string | null; service_catalog_name?: string | null },
  hydrateById: HydrateFn,
): string {
  const id = (svc.service_catalog_id || '').trim();
  const name = (svc.service_catalog_name || '').trim();
  if (name.length > 0) {
    return name;
  }

  if (id.length > 0) {
    const hydrated = hydrateById(id);
    if (hydrated && hydrated.trim().length > 0) {
      return hydrated.trim();
    }
    return `Service ${id}`;
  }

  return 'Service';
}

let catalogCache: CatalogSummary[] | null = null;
let catalogPromise: Promise<CatalogSummary[]> | null = null;

function isPlaceholderLabel(value: string | undefined | null, fallbackId?: string): boolean {
  if (!value) return true;
  const lower = value.trim().toLowerCase();
  if (!lower) return true;
  if (lower === 'unknown service') return true;
  if (fallbackId && lower === `service ${fallbackId}`.toLowerCase()) return true;
  return false;
}

async function loadCatalogServices(): Promise<CatalogSummary[]> {
  if (catalogCache) {
    return catalogCache;
  }

  if (!catalogPromise) {
    catalogPromise = (async () => {
      try {
        const res = await publicApi.getCatalogServices();
        const items = Array.isArray(res.data) ? res.data : [];
        catalogCache = items
          .map((svc) => ({ id: String(svc.id ?? ''), name: String(svc.name ?? '') }))
          .filter((svc) => svc.id && svc.name.trim().length > 0);
        return catalogCache;
      } catch (error) {
        logger.warn('Failed to load catalog services for hydration', error as Error);
        catalogCache = [];
        return catalogCache;
      } finally {
        catalogPromise = null;
      }
    })();
  }

  return catalogPromise;
}

function resolveDisplayName(record: Record<string, unknown>, lookup: Map<string, string>, fallbackId?: string): string {
  const fromServer = typeof record['service_catalog_name'] === 'string' ? record['service_catalog_name'].trim() : '';
  const rawName = typeof record['name'] === 'string' ? record['name'].trim() : '';
  const rawSkill = typeof record['skill'] === 'string' ? record['skill'].trim() : '';

  if (fromServer && !isPlaceholderLabel(fromServer, fallbackId)) {
    return fromServer;
  }
  if (rawName && !isPlaceholderLabel(rawName, fallbackId)) {
    return rawName;
  }
  if (rawSkill && !isPlaceholderLabel(rawSkill, fallbackId)) {
    return rawSkill;
  }

  if (fallbackId) {
    const hydrated = lookup.get(fallbackId);
    if (hydrated && hydrated.trim().length > 0) {
      return hydrated.trim();
    }
  }

  if (fallbackId) {
    return `Service ${fallbackId}`;
  }
  return 'Unknown Service';
}

export async function normalizeInstructorServices(services: unknown): Promise<UIInstructorService[]> {
  if (!Array.isArray(services) || services.length === 0) {
    return [];
  }

  const needsCatalogLookup = services.some((svc) => {
    if (!svc || typeof svc !== 'object') return false;
    const record = svc as Record<string, unknown>;
    const catalogId = typeof record['service_catalog_id'] === 'string' ? record['service_catalog_id'] : undefined;
    if (!catalogId) return false;
    const rawServer = typeof record['service_catalog_name'] === 'string' ? record['service_catalog_name'] : undefined;
    const rawName = typeof record['name'] === 'string' ? record['name'] : undefined;
    const rawSkill = typeof record['skill'] === 'string' ? record['skill'] : undefined;
    return (
      isPlaceholderLabel(rawServer, catalogId) &&
      isPlaceholderLabel(rawName, catalogId) &&
      isPlaceholderLabel(rawSkill, catalogId)
    );
  });

  const catalogList = needsCatalogLookup ? await loadCatalogServices() : catalogCache ?? [];
  const lookup = new Map<string, string>(catalogList.map((svc) => [svc.id, svc.name]));

  return services
    .map((svc, index) => {
      if (!svc || typeof svc !== 'object') return null;
      const record = svc as Record<string, unknown>;
      const catalogIdRaw = typeof record['service_catalog_id'] === 'string' ? record['service_catalog_id'] : undefined;
      const catalogId = catalogIdRaw && catalogIdRaw.trim().length > 0 ? catalogIdRaw : `service-${index}`;
      const displayName = resolveDisplayName(record, lookup, catalogIdRaw);
      const durationOptions = Array.isArray(record['duration_options']) && record['duration_options'].length > 0
        ? (record['duration_options'] as number[])
        : [60];
      const hourlyRate = typeof record['hourly_rate'] === 'number'
        ? record['hourly_rate']
        : Number.parseFloat(String(record['hourly_rate'] ?? '0'));

      const normalized: UIInstructorService = {
        ...(record as unknown as InstructorService),
        service_catalog_id: catalogId,
        service_catalog_name: displayName,
        name: displayName,
        skill: typeof record['skill'] === 'string' && record['skill'].trim().length > 0 ? record['skill'].trim() : displayName,
        duration_options: durationOptions,
        hourly_rate: Number.isFinite(hourlyRate) ? hourlyRate : 0,
        ...(Array.isArray(record['levels_taught']) && record['levels_taught'].length
          ? { levels_taught: (record['levels_taught'] as unknown[]).map((lvl) => String(lvl)) }
          : {}),
        ...(Array.isArray(record['location_types']) && record['location_types'].length
          ? { location_types: (record['location_types'] as unknown[]).map((loc) => String(loc)) }
          : {}),
      };

      return normalized;
    })
    .filter((svc): svc is UIInstructorService => svc !== null);
}

export function hydrateCatalogNameById(serviceCatalogId: string): string | undefined {
  if (!catalogCache || !serviceCatalogId) return undefined;
  const entry = catalogCache.find((svc) => svc.id === serviceCatalogId);
  return entry?.name;
}
