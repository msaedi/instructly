import {
  type ContentFilterSelections,
  type TaxonomyContentFilterDefinition,
  UNIVERSAL_SKILL_LEVEL_OPTIONS,
  type SkillLevelOption,
  type SkillLevelValue,
} from '@/components/search/filterTypes';
import type { SubcategoryFilterResponse } from '@/features/shared/api/types';
import { formatFilterLabel } from '@/lib/taxonomy/formatFilterLabel';

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
const ULID_REGEX = /^[0-9A-HJKMNP-TV-Z]{26}$/i;

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

const normalizeContentFilterKey = (value?: string | null): string | null =>
  parseNonEmpty(value)?.toLowerCase() ?? null;

const normalizeContentFilterValue = (value?: string | null): string | null =>
  parseNonEmpty(value)?.toLowerCase() ?? null;

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
    const resolvedExplicit = resolveSubcategoryParam(explicitSubcategoryId, input.lookup);
    if (resolvedExplicit) {
      return {
        resolvedSubcategoryId: resolvedExplicit,
        inferredSubcategoryId: null,
      };
    }

    const inferredFromService = inferSubcategoryFromService(input);
    if (inferredFromService) {
      return {
        resolvedSubcategoryId: inferredFromService,
        inferredSubcategoryId: inferredFromService,
      };
    }

    // Keep ULID-like explicit values as-is to preserve direct-link behavior.
    if (ULID_REGEX.test(explicitSubcategoryId)) {
      return {
        resolvedSubcategoryId: explicitSubcategoryId,
        inferredSubcategoryId: null,
      };
    }

    return {
      resolvedSubcategoryId: null,
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

export const parseContentFiltersParam = (value?: string | null): ContentFilterSelections => {
  const rawValue = parseNonEmpty(value);
  if (!rawValue) return {};

  const parsed: ContentFilterSelections = {};
  for (const segment of rawValue.split('|')) {
    const normalizedSegment = segment.trim();
    if (!normalizedSegment) continue;

    const colonIndex = normalizedSegment.indexOf(':');
    if (colonIndex <= 0) continue;

    const normalizedKey = normalizeContentFilterKey(normalizedSegment.slice(0, colonIndex));
    if (!normalizedKey) continue;

    const rawValues = normalizedSegment
      .slice(colonIndex + 1)
      .split(',')
      .map((entry) => normalizeContentFilterValue(entry))
      .filter((entry): entry is string => Boolean(entry));

    if (!rawValues.length) continue;

    const existingValues = parsed[normalizedKey] ?? [];
    const seenValues = new Set(existingValues);
    for (const rawEntry of rawValues) {
      if (seenValues.has(rawEntry)) continue;
      existingValues.push(rawEntry);
      seenValues.add(rawEntry);
    }
    parsed[normalizedKey] = existingValues;
  }

  return parsed;
};

const normalizeContentFilterSelections = (
  selections: ContentFilterSelections
): ContentFilterSelections => {
  const normalized: ContentFilterSelections = {};

  for (const [rawKey, rawValues] of Object.entries(selections)) {
    const normalizedKey = normalizeContentFilterKey(rawKey);
    if (!normalizedKey || !Array.isArray(rawValues)) continue;

    const dedupedValues: string[] = [];
    const seen = new Set<string>();
    for (const rawValue of rawValues) {
      const normalizedValue = normalizeContentFilterValue(rawValue);
      if (!normalizedValue || seen.has(normalizedValue)) continue;
      dedupedValues.push(normalizedValue);
      seen.add(normalizedValue);
    }

    if (dedupedValues.length > 0) {
      normalized[normalizedKey] = dedupedValues;
    }
  }

  return normalized;
};

export const buildContentFiltersParam = (
  selections: ContentFilterSelections,
  orderedKeys: string[] = []
): string | null => {
  const normalizedSelections = normalizeContentFilterSelections(selections);
  const keys = Object.keys(normalizedSelections);
  if (!keys.length) return null;

  const orderedKeyList: string[] = [];
  const normalizedOrder = orderedKeys
    .map((key) => normalizeContentFilterKey(key))
    .filter((key): key is string => Boolean(key));

  for (const key of normalizedOrder) {
    if (normalizedSelections[key]) {
      orderedKeyList.push(key);
    }
  }

  const orderedSet = new Set(orderedKeyList);
  const remaining = keys.filter((key) => !orderedSet.has(key)).sort();
  const finalOrder = [...orderedKeyList, ...remaining];
  const segments = finalOrder
    .map((key) => {
      const values = normalizedSelections[key];
      if (!values || values.length === 0) return null;
      return `${key}:${values.join(',')}`;
    })
    .filter((segment): segment is string => Boolean(segment));
  return segments.length > 0 ? segments.join('|') : null;
};

export const getDynamicContentFiltersFromTaxonomy = (
  filters: SubcategoryFilterResponse[] | undefined
): TaxonomyContentFilterDefinition[] => {
  if (!filters || filters.length === 0) {
    return [];
  }

  const definitions: TaxonomyContentFilterDefinition[] = [];
  for (const filter of filters) {
    const key = normalizeContentFilterKey(filter.filter_key);
    if (!key || key === 'skill_level') continue;

    const options: TaxonomyContentFilterDefinition['options'] = [];
    const seen = new Set<string>();
    for (const option of filter.options ?? []) {
      const normalizedValue = normalizeContentFilterValue(option.value);
      if (!normalizedValue || seen.has(normalizedValue)) continue;
      options.push({
        value: normalizedValue,
        label: formatFilterLabel(normalizedValue, option.display_name),
      });
      seen.add(normalizedValue);
    }

    if (options.length === 0) continue;
    definitions.push({
      key,
      label: parseNonEmpty(filter.filter_display_name) ?? formatFilterLabel(key),
      options,
    });
  }

  return definitions;
};

export const sanitizeContentFiltersForSubcategory = (
  selections: ContentFilterSelections,
  filters: SubcategoryFilterResponse[] | undefined
): ContentFilterSelections => {
  const normalizedSelections = normalizeContentFilterSelections(selections);
  const definitions = getDynamicContentFiltersFromTaxonomy(filters);
  if (!definitions.length) {
    return {};
  }

  const allowedValuesByKey = new Map<string, Set<string>>();
  for (const definition of definitions) {
    allowedValuesByKey.set(
      definition.key,
      new Set(definition.options.map((option) => option.value))
    );
  }

  const sanitized: ContentFilterSelections = {};
  for (const [key, values] of Object.entries(normalizedSelections)) {
    const allowedValues = allowedValuesByKey.get(key);
    if (!allowedValues) continue;

    const keptValues = values.filter((value) => allowedValues.has(value));
    if (keptValues.length > 0) {
      sanitized[key] = keptValues;
    }
  }

  return sanitized;
};
