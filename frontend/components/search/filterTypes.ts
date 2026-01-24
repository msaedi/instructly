export type FilterState = {
  date: string | null;
  timeOfDay: Array<'morning' | 'afternoon' | 'evening'>;
  duration: Array<30 | 45 | 60>;
  priceMin: number | null;
  priceMax: number | null;
  location: 'any' | 'online' | 'travels' | 'studio';
  level: Array<'beginner' | 'intermediate' | 'advanced'>;
  audience: Array<'adults' | 'kids'>;
  minRating: 'any' | '4' | '4.5';
};

export const DEFAULT_FILTERS: FilterState = {
  date: null,
  timeOfDay: [],
  duration: [],
  priceMin: null,
  priceMax: null,
  location: 'any',
  level: [],
  audience: [],
  minRating: 'any',
};
