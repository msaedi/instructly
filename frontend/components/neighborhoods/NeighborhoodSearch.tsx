import { Search } from 'lucide-react';

type NeighborhoodSearchProps = {
  query: string;
  onQueryChange: (value: string) => void;
  placeholder?: string;
};

export function NeighborhoodSearch({
  query,
  onQueryChange,
  placeholder = 'Search neighborhoods...',
}: NeighborhoodSearchProps) {
  return (
    <label className="relative block">
      <span className="sr-only">Search neighborhoods</span>
      <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        type="text"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-2xl border border-gray-200 bg-white/90 py-3 pl-11 pr-4 text-sm text-gray-900 shadow-sm outline-none transition-colors duration-150 placeholder:text-gray-400 focus:border-(--color-brand-dark) focus:ring-2 focus:ring-purple-100 dark:border-gray-700 dark:bg-gray-900/80 dark:text-gray-100 dark:placeholder:text-gray-500"
        data-testid="neighborhood-search-input"
      />
    </label>
  );
}
