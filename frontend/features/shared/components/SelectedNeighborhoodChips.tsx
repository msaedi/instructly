import { X } from 'lucide-react';

export type SelectedNeighborhood = {
  neighborhood_id: string;
  name: string;
};

export type SelectedNeighborhoodChipsProps = {
  selected: SelectedNeighborhood[];
  onRemove: (id: string) => void;
};

export function SelectedNeighborhoodChips({ selected, onRemove }: SelectedNeighborhoodChipsProps) {
  if (!selected.length) return null;

  return (
    <div className="flex flex-wrap gap-2" data-testid="selected-neighborhood-chip-list">
      {selected.map((item) => (
        <span
          key={item.neighborhood_id}
          className="inline-flex items-center gap-2 rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-sm font-medium text-[#7E22CE]"
          data-testid="selected-neighborhood-chip"
        >
          <span className="truncate max-w-[12rem]" title={item.name}>
            {item.name || 'Neighborhood'}
          </span>
          <button
            type="button"
            onClick={() => onRemove(item.neighborhood_id)}
            aria-label={`Remove ${item.name || 'neighborhood'}`}
            className="inline-flex h-5 w-5 items-center justify-center rounded-full text-[#7E22CE] hover:bg-purple-100"
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </span>
      ))}
    </div>
  );
}
