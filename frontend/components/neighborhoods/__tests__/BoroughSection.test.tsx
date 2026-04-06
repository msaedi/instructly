import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { BoroughSection } from '../BoroughSection';
import type { SelectorDisplayItem } from '@/features/shared/api/types';

function makeItem(
  item: Partial<SelectorDisplayItem> &
    Pick<SelectorDisplayItem, 'display_key' | 'display_name' | 'borough'>,
): SelectorDisplayItem {
  return {
    additional_boroughs: item.additional_boroughs ?? [],
    display_key: item.display_key,
    display_name: item.display_name,
    display_order: item.display_order ?? 0,
    borough: item.borough,
    nta_ids: item.nta_ids ?? [item.display_key],
    search_terms: item.search_terms ?? [],
  };
}

describe('BoroughSection', () => {
  it('renders the default empty state when optional search props are omitted', () => {
    render(
      <BoroughSection
        borough="Queens"
        items={[]}
        selectedKeys={new Set()}
        onToggle={jest.fn()}
        onSelectAll={jest.fn()}
        onClearAll={jest.fn()}
        isExpanded
        onToggleExpand={jest.fn()}
        selectionMode="multi"
      />,
    );

    expect(screen.getByTestId('neighborhood-borough-queens')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByText('No neighborhoods available.')).toBeInTheDocument();
    expect(screen.queryByText('No matches')).not.toBeInTheDocument();
  });

  it('renders the search-specific empty state when no items match', () => {
    render(
      <BoroughSection
        borough="Queens"
        items={[]}
        selectedKeys={new Set()}
        onToggle={jest.fn()}
        onSelectAll={jest.fn()}
        onClearAll={jest.fn()}
        isExpanded
        onToggleExpand={jest.fn()}
        selectionMode="multi"
        searchActive
      />,
    );

    expect(screen.getByText('No matches')).toBeInTheDocument();
    expect(screen.getByText('No neighborhoods match this search.')).toBeInTheDocument();
  });

  it('shows inline alias hints for long names and wires chip, hover, and bulk actions', async () => {
    const onToggle = jest.fn();
    const onHoverKey = jest.fn();
    const onSelectAll = jest.fn();
    const onClearAll = jest.fn();
    const user = userEvent.setup();
    const item = makeItem({
      borough: 'Queens',
      display_key: 'rockaway',
      display_name: 'Rockaway Park / Belle Harbor / Broad Channel / Breezy Point',
      display_order: 1,
      search_terms: [
        {
          term: 'Rockaway Park / Belle Harbor / Broad Channel / Breezy Point',
          type: 'display_part',
        },
      ],
    });

    render(
      <BoroughSection
        borough="Queens"
        items={[item]}
        selectedKeys={new Set([item.display_key])}
        onToggle={onToggle}
        onSelectAll={onSelectAll}
        onClearAll={onClearAll}
        isExpanded
        onToggleExpand={jest.fn()}
        selectionMode="multi"
        searchActive
        onHoverKey={onHoverKey}
        matchInfo={new Map([[item.display_key, 'Belle Harbor']])}
      />,
    );

    const chip = screen.getByTestId('neighborhood-chip-rockaway');
    expect(chip).toHaveAttribute('title', 'Matches: Belle Harbor');
    expect(within(chip).getByText('Matches: Belle Harbor')).toBeInTheDocument();

    await user.hover(chip);
    await user.unhover(chip);
    await user.click(chip);
    await user.click(screen.getByRole('button', { name: 'Select all' }));
    await user.click(screen.getByRole('button', { name: 'Clear all' }));

    expect(onHoverKey).toHaveBeenNthCalledWith(1, 'rockaway');
    expect(onHoverKey).toHaveBeenNthCalledWith(2, null);
    expect(onToggle).toHaveBeenCalledWith('rockaway');
    expect(onSelectAll).toHaveBeenCalledTimes(1);
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });
});
