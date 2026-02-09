import {
  UNIVERSAL_SKILL_LEVEL_OPTIONS,
  type SkillLevelOption,
  type SkillLevelValue,
} from '@/components/search/filterTypes';
import type { SubcategoryFilterResponse } from '@/features/shared/api/types';

export type SubcategoryResolutionLookup = {
  subcategoryIds: Set<string>;
  subcategoryIdsByLower: Map<string, string>;
  subcategoryByName: Map<string, string>;
  serviceByCatalogId: Map<string, string>;
  serviceBySlug: Map<string, string>;
  serviceByName: Map<string, string>;
};

type ResolveSubcategoryContextInput = {
  explicitSubcategoryId?: string | null;
  subcategoryParam?: string | null;
  serviceCatalogId?: string | null;
  serviceParam?: string | null;
  serviceName?: string | null;
  lookup: SubcategoryResolutionLookup;
};

type ResolveSubcategoryContextResult = {
  resolvedSubcategoryId: string | null;
  inferredSubcategoryId: string | null;
};

const SKILL_LEVEL_SET = new Set<SkillLevelValue>(['beginner', 'intermediate', 'advanced']);

const parseNonEmpty = (value?: string | null): string | null => {
  if (!value) return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const normalizeSkillLevelValue = (value?: string | null): SkillLevelValue | null => {
  const parsed = parseNonEmpty(value)?.toLowerCase();
  if (!parsed) return null;
  return SKILL_LEVEL_SET.has(parsed as SkillLevelValue) ? (parsed as SkillLevelValue) : null;
};

export const normalizeLookupKey = (value: string): string =>
  value.trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');

const resolveSubcategoryParam = (
  rawSubcategory: string | null | undefined,
  lookup: SubcategoryResolutionLookup
): string | null => {
  const subcategory = parseNonEmpty(rawSubcategory);
  if (!subcategory) return null;

  if (lookup.subcategoryIds.has(subcategory)) {
    return subcategory;
  }

  const lowerMatch = lookup.subcategoryIdsByLower.get(subcategory.toLowerCase());
  if (lowerMatch) {
    return lowerMatch;
  }

  return lookup.subcategoryByName.get(normalizeLookupKey(subcategory)) ?? null;
};

const inferSubcategoryFromService = (
  input: Pick<
    ResolveSubcategoryContextInput,
    'serviceCatalogId' | 'serviceParam' | 'serviceName' | 'lookup'
  >
): string | null => {
  const { serviceCatalogId, serviceParam, serviceName, lookup } = input;

  const catalogMatch = parseNonEmpty(serviceCatalogId);
  if (catalogMatch) {
    const inferredByCatalogId = lookup.serviceByCatalogId.get(catalogMatch.toLowerCase());
    if (inferredByCatalogId) {
      return inferredByCatalogId;
    }
  }

  const serviceValue = parseNonEmpty(serviceParam);
  if (serviceValue) {
    const lowerService = serviceValue.toLowerCase();
    const inferredByServiceId = lookup.serviceByCatalogId.get(lowerService);
    if (inferredByServiceId) {
      return inferredByServiceId;
    }

    const normalizedService = normalizeLookupKey(serviceValue);
    const inferredBySlug = lookup.serviceBySlug.get(normalizedService);
    if (inferredBySlug) {
      return inferredBySlug;
    }

    const inferredByName = lookup.serviceByName.get(normalizedService);
    if (inferredByName) {
      return inferredByName;
    }
  }

  const serviceNameValue = parseNonEmpty(serviceName);
  if (!serviceNameValue) {
    return null;
  }

  return lookup.serviceByName.get(normalizeLookupKey(serviceNameValue)) ?? null;
};

export const resolveSubcategoryContext = (
  input: ResolveSubcategoryContextInput
): ResolveSubcategoryContextResult => {
  const explicitSubcategoryId = parseNonEmpty(input.explicitSubcategoryId);
  if (explicitSubcategoryId) {
    return {
      resolvedSubcategoryId: explicitSubcategoryId,
      inferredSubcategoryId: null,
    };
  }

  const resolvedFromParam = resolveSubcategoryParam(input.subcategoryParam, input.lookup);
  if (resolvedFromParam) {
    return {
      resolvedSubcategoryId: resolvedFromParam,
      inferredSubcategoryId: null,
    };
  }

  const inferredSubcategoryId = inferSubcategoryFromService(input);
  return {
    resolvedSubcategoryId: inferredSubcategoryId,
    inferredSubcategoryId,
  };
};

export const parseSkillLevelParam = (value?: string | null): SkillLevelValue[] => {
  const rawValue = parseNonEmpty(value);
  if (!rawValue) return [];

  const unique = new Set<SkillLevelValue>();
  rawValue.split(',').forEach((entry) => {
    const parsed = normalizeSkillLevelValue(entry);
    if (parsed) {
      unique.add(parsed);
    }
  });

  return Array.from(unique);
};

export const getSkillLevelOptionsFromTaxonomy = (
  filters: SubcategoryFilterResponse[] | undefined
): SkillLevelOption[] => {
  const skillLevelFilter = filters?.find((filter) => filter.filter_key === 'skill_level');
  if (!skillLevelFilter?.options || skillLevelFilter.options.length === 0) {
    return UNIVERSAL_SKILL_LEVEL_OPTIONS;
  }

  const options: SkillLevelOption[] = [];
  const seen = new Set<SkillLevelValue>();
  for (const option of skillLevelFilter.options) {
    const normalizedValue = normalizeSkillLevelValue(option.value);
    if (!normalizedValue || seen.has(normalizedValue)) continue;
    options.push({
      value: normalizedValue,
      label: option.display_name,
    });
    seen.add(normalizedValue);
  }

  return options.length > 0 ? options : UNIVERSAL_SKILL_LEVEL_OPTIONS;
};

export const buildSkillLevelParam = (
  selectedLevels: SkillLevelValue[],
  allOptions: SkillLevelOption[]
): string | null => {
  if (!selectedLevels.length) return null;

  const optionOrder = allOptions
    .map((option) => normalizeSkillLevelValue(option.value))
    .filter((value): value is SkillLevelValue => Boolean(value));
  if (!optionOrder.length) return null;

  const selectedSet = new Set<SkillLevelValue>();
  selectedLevels.forEach((level) => {
    const normalized = normalizeSkillLevelValue(level);
    if (normalized) {
      selectedSet.add(normalized);
    }
  });
  if (!selectedSet.size) return null;

  const orderedSelected = optionOrder.filter((value) => selectedSet.has(value));
  if (!orderedSelected.length || orderedSelected.length === optionOrder.length) {
    return null;
  }

  return orderedSelected.join(',');
};
