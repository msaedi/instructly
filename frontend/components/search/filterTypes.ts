export type SkillLevelValue = 'beginner' | 'intermediate' | 'advanced';

export type SkillLevelOption = {
  value: SkillLevelValue;
  label: string;
};

export type ContentFilterSelections = Record<string, string[]>;

export type TaxonomyContentFilterOption = {
  value: string;
  label: string;
};

export type TaxonomyContentFilterDefinition = {
  key: string;
  label: string;
  options: TaxonomyContentFilterOption[];
};

export const UNIVERSAL_SKILL_LEVEL_OPTIONS: SkillLevelOption[] = [
  { value: 'beginner', label: 'Beginner' },
  { value: 'intermediate', label: 'Intermediate' },
  { value: 'advanced', label: 'Advanced' },
];

export type FilterState = {
  date: string | null;
  timeOfDay: Array<'morning' | 'afternoon' | 'evening'>;
  duration: Array<30 | 45 | 60>;
  priceMin: number | null;
  priceMax: number | null;
  location: 'any' | 'online' | 'travels' | 'studio';
  skillLevel: SkillLevelValue[];
  contentFilters: ContentFilterSelections;
  minRating: 'any' | '4' | '4.5';
};

export const DEFAULT_FILTERS: FilterState = {
  date: null,
  timeOfDay: [],
  duration: [],
  priceMin: null,
  priceMax: null,
  location: 'any',
  skillLevel: [],
  contentFilters: {},
  minRating: 'any',
};
