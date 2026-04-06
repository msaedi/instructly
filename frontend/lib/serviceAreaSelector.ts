import type {
  NeighborhoodSelectorResponse,
  SelectorDisplayItem,
  ServiceAreaItem,
} from '@/features/shared/api/types';

export type ServiceAreaSelectorIndex = {
  boroughNeighborhoods: Record<string, ServiceAreaItem[]>;
  idToItem: Record<string, ServiceAreaItem>;
  items: ServiceAreaItem[];
};

export function mapSelectorDisplayItem(item: SelectorDisplayItem): ServiceAreaItem {
  return {
    borough: item.borough,
    display_key: item.display_key,
    display_name: item.display_name,
  };
}

export function buildServiceAreaSelectorIndex(
  response: NeighborhoodSelectorResponse,
): ServiceAreaSelectorIndex {
  const boroughNeighborhoods: Record<string, ServiceAreaItem[]> = {};
  const idToItem: Record<string, ServiceAreaItem> = {};
  const items: ServiceAreaItem[] = [];

  for (const boroughGroup of response.boroughs) {
    const boroughItems = boroughGroup.items.map(mapSelectorDisplayItem);
    boroughNeighborhoods[boroughGroup.borough] = boroughItems;

    for (const item of boroughItems) {
      idToItem[item.display_key] = item;
      items.push(item);
    }
  }

  return { boroughNeighborhoods, idToItem, items };
}
