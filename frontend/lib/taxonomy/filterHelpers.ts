/**
 * Shared taxonomy filter constants, types, and normalization helpers.
 *
 * Used by both the onboarding skill-selection page and the instructor
 * dashboard SkillsPricingInline component.
 */

export const ALL_AUDIENCE_GROUPS = ['toddler', 'kids', 'teens', 'adults'] as const;
export type AudienceGroup = (typeof ALL_AUDIENCE_GROUPS)[number];

export const AUDIENCE_LABELS: Record<AudienceGroup, string> = {
  toddler: 'Toddler',
  kids: 'Kids',
  teens: 'Teens',
  adults: 'Adults',
};

export const DEFAULT_SKILL_LEVELS = ['beginner', 'intermediate', 'advanced'] as const;
export type SkillLevel = (typeof DEFAULT_SKILL_LEVELS)[number];

export type FilterSelections = Record<string, string[]>;

export const toAudienceGroup = (value: unknown): AudienceGroup | null => {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  if (ALL_AUDIENCE_GROUPS.includes(normalized as AudienceGroup)) {
    return normalized as AudienceGroup;
  }
  return null;
};

export const dedupeAudienceGroups = (groups: AudienceGroup[]): AudienceGroup[] => {
  const groupSet = new Set(groups);
  return ALL_AUDIENCE_GROUPS.filter((group) => groupSet.has(group));
};

export const normalizeAudienceGroups = (
  value: unknown,
  fallback: AudienceGroup[] = []
): AudienceGroup[] => {
  const fallbackGroups = dedupeAudienceGroups(fallback);
  if (!Array.isArray(value)) {
    return fallbackGroups;
  }

  const normalized = dedupeAudienceGroups(
    value
      .map((entry) => toAudienceGroup(entry))
      .filter((entry): entry is AudienceGroup => entry !== null)
  );

  return normalized.length > 0 ? normalized : fallbackGroups;
};

export const normalizeSkillLevels = (
  value: unknown,
  fallback: SkillLevel[] = [...DEFAULT_SKILL_LEVELS]
): SkillLevel[] => {
  if (!Array.isArray(value)) {
    return [...fallback];
  }

  const normalized = value
    .map((entry) => (typeof entry === 'string' ? entry.trim().toLowerCase() : ''))
    .filter((entry): entry is SkillLevel =>
      DEFAULT_SKILL_LEVELS.includes(entry as SkillLevel)
    );

  const unique = DEFAULT_SKILL_LEVELS.filter((level) => normalized.includes(level));
  return unique.length > 0 ? unique : [...fallback];
};

export const normalizeSelectionValues = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  const normalized = value
    .map((entry) => (typeof entry === 'string' ? entry.trim() : String(entry).trim()))
    .filter((entry) => entry.length > 0);
  return Array.from(new Set(normalized));
};

export const normalizeFilterSelections = (value: unknown): FilterSelections => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }

  const result: FilterSelections = {};
  for (const [key, rawValues] of Object.entries(value as Record<string, unknown>)) {
    const normalized = normalizeSelectionValues(rawValues);
    if (normalized.length > 0) {
      result[key] = normalized;
    }
  }
  return result;
};

export const defaultFilterSelections = (eligibleAgeGroups: AudienceGroup[]): FilterSelections => ({
  skill_level: [...DEFAULT_SKILL_LEVELS],
  age_groups:
    eligibleAgeGroups.length > 0 ? [...eligibleAgeGroups] : [...ALL_AUDIENCE_GROUPS],
});

export const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim().length > 0;

export const arraysEqual = (a: readonly string[], b: readonly string[]): boolean => {
  if (a.length !== b.length) {
    return false;
  }
  return a.every((value, index) => value === b[index]);
};
