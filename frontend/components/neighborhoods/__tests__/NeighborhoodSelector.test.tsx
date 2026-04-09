import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { NeighborhoodSelector } from '../NeighborhoodSelector';
import type {
  NeighborhoodSelectorResponse,
  SelectorDisplayItem,
} from '@/features/shared/api/types';
import { useNeighborhoodSelectorData } from '@/hooks/queries/useNeighborhoodSelectorData';
import { useNeighborhoodPolygons } from '@/hooks/queries/useNeighborhoodPolygons';

jest.mock('next/dynamic', () => {
  return (loader: () => Promise<unknown>) => {
    void loader();
    const MockComponent = require('../NeighborhoodSelectorMap').default as React.ComponentType<{
      featureCollection?: unknown;
      selectedKeys: Set<string>;
      hoveredKey?: string | null;
      onHoverKey?: (key: string | null) => void;
      onToggleKey: (key: string) => void;
    }>;
    return function DynamicNeighborhoodSelectorMap(props: {
      featureCollection?: unknown;
      selectedKeys: Set<string>;
      hoveredKey?: string | null;
      onHoverKey?: (key: string | null) => void;
      onToggleKey: (key: string) => void;
    }) {
      return <MockComponent {...props} />;
    };
  };
});

jest.mock('../NeighborhoodSelectorMap', () => ({
  __esModule: true,
  default: ({
    featureCollection,
    selectedKeys,
    hoveredKey,
    onHoverKey,
    onToggleKey,
  }: {
    featureCollection?: unknown;
    selectedKeys: Set<string>;
    hoveredKey?: string | null;
    onHoverKey?: (key: string | null) => void;
    onToggleKey: (key: string) => void;
  }) => (
    <div data-testid="selector-map">
      <div data-testid="map-feature-collection">{featureCollection ? 'present' : 'null'}</div>
      <div data-testid="map-selected">{Array.from(selectedKeys).join(',')}</div>
      <div data-testid="map-hovered">{hoveredKey ?? ''}</div>
      <button type="button" onClick={() => onHoverKey?.('ues')}>
        Hover Map UES
      </button>
      <button type="button" onClick={() => onToggleKey('marble')}>
        Toggle Map Marble
      </button>
    </div>
  ),
}));

jest.mock('@/hooks/queries/useNeighborhoodSelectorData', () => ({
  useNeighborhoodSelectorData: jest.fn(),
}));

jest.mock('@/hooks/queries/useNeighborhoodPolygons', () => ({
  useNeighborhoodPolygons: jest.fn(),
}));

const useNeighborhoodSelectorDataMock = useNeighborhoodSelectorData as jest.MockedFunction<
  typeof useNeighborhoodSelectorData
>;
const useNeighborhoodPolygonsMock = useNeighborhoodPolygons as jest.MockedFunction<
  typeof useNeighborhoodPolygons
>;

function makeItem(
  item: Partial<SelectorDisplayItem> & Pick<SelectorDisplayItem, 'display_key' | 'display_name' | 'borough'>,
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

const selectorResponse: NeighborhoodSelectorResponse = {
  market: 'nyc',
  total_items: 6,
  boroughs: [
    {
      borough: 'Manhattan',
      item_count: 2,
      items: [
        makeItem({
          borough: 'Manhattan',
          display_key: 'ues',
          display_name: 'Upper East Side',
          display_order: 1,
          search_terms: [
            { term: 'Upper East Side', type: 'display_part' },
            { term: 'Yorkville', type: 'raw_nta' },
          ],
        }),
        makeItem({
          borough: 'Manhattan',
          display_key: 'chelsea',
          display_name: 'Chelsea',
          display_order: 2,
          search_terms: [{ term: 'Chelsea', type: 'display_part' }],
        }),
      ],
    },
    {
      borough: 'Brooklyn',
      item_count: 0,
      items: [],
    },
    {
      borough: 'Queens',
      item_count: 2,
      items: [
        makeItem({
          borough: 'Queens',
          display_key: 'south-jamaica',
          display_name: 'South Jamaica',
          display_order: 1,
          search_terms: [
            { term: 'South Jamaica', type: 'display_part' },
            { term: 'Baisley Park', type: 'hidden_subarea' },
          ],
        }),
        makeItem({
          borough: 'Queens',
          display_key: 'rockaway',
          display_name: 'Rockaway Park / Belle Harbor / Broad Channel / Breezy Point',
          display_order: 2,
          search_terms: [
            {
              term: 'Rockaway Park / Belle Harbor / Broad Channel / Breezy Point',
              type: 'display_part',
            },
          ],
        }),
      ],
    },
    {
      borough: 'Bronx',
      item_count: 1,
      items: [
        makeItem({
          borough: 'Bronx',
          display_key: 'marble',
          display_name: 'Kingsbridge / Marble Hill',
          display_order: 1,
          additional_boroughs: ['Manhattan'],
          search_terms: [
            { term: 'Kingsbridge', type: 'display_part' },
            { term: 'Marble Hill', type: 'hidden_subarea' },
          ],
        }),
      ],
    },
    {
      borough: 'Staten Island',
      item_count: 1,
      items: [
        makeItem({
          borough: 'Staten Island',
          display_key: 'princes-bay',
          display_name: "Prince's Bay",
          display_order: 1,
          search_terms: [{ term: "Prince's Bay", type: 'display_part' }],
        }),
      ],
    },
  ],
};

const allItems = selectorResponse.boroughs.flatMap((borough) => borough.items);
const itemByKey = new Map(allItems.map((item) => [item.display_key, item]));
const boroughs = selectorResponse.boroughs.map((borough) => borough.borough);

function renderSelector(props?: Partial<React.ComponentProps<typeof NeighborhoodSelector>>) {
  return render(
    <NeighborhoodSelector
      showMap={false}
      {...props}
    />,
  );
}

describe('NeighborhoodSelector', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: selectorResponse,
      isLoading: false,
      isError: false,
      allItems,
      itemByKey,
      boroughs,
    } as unknown as ReturnType<typeof useNeighborhoodSelectorData>);
    useNeighborhoodPolygonsMock.mockReturnValue({
      data: {
        type: 'FeatureCollection',
        features: [],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useNeighborhoodPolygons>);
  });

  it('resyncs controlled selection when value changes after mount', () => {
    const { rerender } = renderSelector({ value: [] });

    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'false');

    rerender(<NeighborhoodSelector showMap={false} value={['ues']} />);

    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'true');
  });

  it('replaces the previous selection in single-select mode', async () => {
    renderSelector({ selectionMode: 'single' });
    const user = userEvent.setup();

    await user.click(screen.getByTestId('neighborhood-chip-ues'));
    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByTestId('neighborhood-chip-chelsea'));

    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('neighborhood-chip-chelsea')).toHaveAttribute('aria-pressed', 'true');
  });

  it('stays interactive in controlled mode for both chips and map toggles while preserving the last multi-select item', async () => {
    function ControlledHarness() {
      const [value, setValue] = React.useState<string[]>([]);

      return (
        <NeighborhoodSelector
          showMap
          value={value}
          onSelectionChange={(keys) => {
            setValue(keys);
          }}
        />
      );
    }

    render(<ControlledHarness />);
    const user = userEvent.setup();

    await user.click(screen.getByTestId('neighborhood-chip-ues'));
    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('map-selected')).toHaveTextContent('ues');

    await user.click(screen.getByRole('button', { name: 'Toggle Map Marble' }));
    await user.click(screen.getByTestId('neighborhood-borough-bronx'));
    expect(screen.getByTestId('neighborhood-chip-marble')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('map-selected')).toHaveTextContent('ues,marble');

    await user.click(screen.getByTestId('neighborhood-borough-manhattan'));
    await user.click(screen.getByTestId('neighborhood-chip-ues'));
    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('map-selected')).toHaveTextContent('marble');

    await user.click(screen.getByRole('button', { name: 'Toggle Map Marble' }));
    await user.click(screen.getByTestId('neighborhood-borough-bronx'));
    expect(screen.getByTestId('neighborhood-chip-marble')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('map-selected')).toHaveTextContent('marble');
  });

  it('renders the apply-specific copy and placeholder', () => {
    renderSelector({ context: 'apply' });

    expect(
      screen.getByRole('heading', { name: 'Choose your primary neighborhood' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Pick the main neighborhood you plan to teach in.'),
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search NYC neighborhoods...')).toBeInTheDocument();
  });

  it('matches hidden-subarea aliases like Baisley Park', async () => {
    renderSelector();
    const user = userEvent.setup();

    await user.type(screen.getByTestId('neighborhood-search-input'), 'Baisley Park');

    expect(screen.getByText('South Jamaica')).toBeInTheDocument();
    expect(screen.getByTestId('neighborhood-borough-queens')).toHaveAttribute('aria-expanded', 'true');
  });

  it('renders Marble Hill in both Bronx and Manhattan during search', async () => {
    const { container } = renderSelector();
    const user = userEvent.setup();
    const liveRegion = container.querySelector('[aria-live="polite"]');

    expect(liveRegion).not.toBeNull();
    expect(liveRegion).toHaveTextContent('');

    await user.type(screen.getByTestId('neighborhood-search-input'), 'Marble Hill');

    expect(screen.getAllByText('Kingsbridge / Marble Hill')).toHaveLength(2);
    expect(screen.getByTestId('neighborhood-borough-manhattan')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByTestId('neighborhood-borough-bronx')).toHaveAttribute('aria-expanded', 'true');
    expect(liveRegion).toHaveTextContent('1 neighborhoods found');
  });

  it('renders Upper East Side and Upper East Side / Roosevelt Island as separate chips', async () => {
    const upperEastSide = makeItem({
      borough: 'Manhattan',
      display_key: 'nyc-manhattan-upper-east-side',
      display_name: 'Upper East Side',
      display_order: 1,
      search_terms: [{ term: 'Upper East Side', type: 'display_part' }],
    });
    const upperEastSideRooseveltIsland = makeItem({
      borough: 'Manhattan',
      display_key: 'nyc-manhattan-upper-east-side-roosevelt-island',
      display_name: 'Upper East Side / Roosevelt Island',
      display_order: 2,
      search_terms: [
        { term: 'Upper East Side / Roosevelt Island', type: 'display_part' },
      ],
    });
    const customResponse: NeighborhoodSelectorResponse = {
      market: 'nyc',
      total_items: 2,
      boroughs: [
        {
          borough: 'Manhattan',
          item_count: 2,
          items: [upperEastSide, upperEastSideRooseveltIsland],
        },
      ],
    };
    const customItems = customResponse.boroughs.flatMap((borough) => borough.items);
    const customItemByKey = new Map(customItems.map((item) => [item.display_key, item]));

    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: customResponse,
      isLoading: false,
      isError: false,
      allItems: customItems,
      itemByKey: customItemByKey,
      boroughs: ['Manhattan'],
    } as unknown as ReturnType<typeof useNeighborhoodSelectorData>);

    renderSelector();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('neighborhood-chip-nyc-manhattan-upper-east-side'));

    expect(
      screen.getByTestId('neighborhood-chip-nyc-manhattan-upper-east-side'),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.getByTestId('neighborhood-chip-nyc-manhattan-upper-east-side-roosevelt-island'),
    ).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Upper East Side')).toBeInTheDocument();
    expect(screen.getByText('Upper East Side / Roosevelt Island')).toBeInTheDocument();
  });

  it('renders chips without plus or checkmark icons', async () => {
    renderSelector({ defaultValue: ['ues'] });
    const user = userEvent.setup();

    const selectedChip = screen.getByTestId('neighborhood-chip-ues');
    expect(selectedChip).toHaveTextContent('Upper East Side');
    expect(within(selectedChip).queryByText('+')).not.toBeInTheDocument();
    expect(within(selectedChip).queryByText('✓')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('neighborhood-borough-manhattan'));
    await user.click(screen.getByTestId('neighborhood-borough-manhattan'));

    const unselectedChip = screen.getByTestId('neighborhood-chip-chelsea');
    expect(unselectedChip).toHaveTextContent('Chelsea');
    expect(within(unselectedChip).queryByText('+')).not.toBeInTheDocument();
    expect(within(unselectedChip).queryByText('✓')).not.toBeInTheDocument();
  });

  it('limits Select all to currently filtered items', async () => {
    renderSelector();
    const user = userEvent.setup();

    await user.type(screen.getByTestId('neighborhood-search-input'), 'upper');
    await user.click(screen.getByRole('button', { name: 'Select all' }));

    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'true');

    await user.clear(screen.getByTestId('neighborhood-search-input'));

    expect(screen.getByTestId('neighborhood-chip-chelsea')).toHaveAttribute('aria-pressed', 'false');
  });

  it('limits Clear all to currently filtered items', async () => {
    renderSelector({ defaultValue: ['ues', 'chelsea'] });
    const user = userEvent.setup();

    await user.type(screen.getByTestId('neighborhood-search-input'), 'upper');
    await user.click(screen.getByRole('button', { name: 'Clear all' }));
    await user.clear(screen.getByTestId('neighborhood-search-input'));

    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('neighborhood-chip-chelsea')).toHaveAttribute('aria-pressed', 'true');
  });

  it('supports a single expanded borough in browse mode', async () => {
    renderSelector();
    const user = userEvent.setup();

    const manhattanHeader = screen.getByTestId('neighborhood-borough-manhattan');
    const bronxHeader = screen.getByTestId('neighborhood-borough-bronx');
    expect(manhattanHeader).toHaveAttribute('aria-expanded', 'true');
    expect(bronxHeader).toHaveAttribute('aria-expanded', 'false');

    await user.click(bronxHeader);

    expect(bronxHeader).toHaveAttribute('aria-expanded', 'true');
    expect(manhattanHeader).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('neighborhood-chip-ues')).not.toBeInTheDocument();

    await user.click(bronxHeader);

    expect(bronxHeader).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('neighborhood-chip-marble')).not.toBeInTheDocument();
  });

  it('allows all browse-mode boroughs to stay collapsed after a user closes the selected borough', async () => {
    renderSelector({ defaultValue: ['marble'] });
    const user = userEvent.setup();

    const manhattanHeader = screen.getByTestId('neighborhood-borough-manhattan');
    const bronxHeader = screen.getByTestId('neighborhood-borough-bronx');
    const queensHeader = screen.getByTestId('neighborhood-borough-queens');

    await waitFor(() => {
      expect(bronxHeader).toHaveAttribute('aria-expanded', 'true');
    });

    await user.click(bronxHeader);

    expect(bronxHeader).toHaveAttribute('aria-expanded', 'false');
    expect(manhattanHeader).toHaveAttribute('aria-expanded', 'false');
    expect(queensHeader).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByTestId('neighborhood-chip-marble')).not.toBeInTheDocument();
  });

  it('restores the manual expansion state after search clears and ignores header clicks while searching', async () => {
    renderSelector();
    const user = userEvent.setup();

    const manhattanHeader = screen.getByTestId('neighborhood-borough-manhattan');
    const bronxHeader = screen.getByTestId('neighborhood-borough-bronx');

    await user.click(bronxHeader);
    expect(bronxHeader).toHaveAttribute('aria-expanded', 'true');
    expect(manhattanHeader).toHaveAttribute('aria-expanded', 'false');

    await user.type(screen.getByTestId('neighborhood-search-input'), 'upper');
    expect(manhattanHeader).toHaveAttribute('aria-expanded', 'true');

    await user.click(manhattanHeader);
    expect(manhattanHeader).toHaveAttribute('aria-expanded', 'true');

    await user.clear(screen.getByTestId('neighborhood-search-input'));
    expect(manhattanHeader).toHaveAttribute('aria-expanded', 'false');
    expect(bronxHeader).toHaveAttribute('aria-expanded', 'true');
  });

  it('applies the three-tier pill sizing classes', () => {
    const belmont = makeItem({
      borough: 'Bronx',
      display_key: 'belmont',
      display_name: 'Belmont',
      display_order: 1,
      search_terms: [{ term: 'Belmont', type: 'display_part' }],
    });
    const greenwichVillage = makeItem({
      borough: 'Bronx',
      display_key: 'greenwich-village',
      display_name: 'Greenwich Village',
      display_order: 2,
      search_terms: [{ term: 'Greenwich Village', type: 'display_part' }],
    });
    const eastchester = makeItem({
      borough: 'Bronx',
      display_key: 'eastchester',
      display_name: 'Eastchester / Edenwald / Baychester',
      display_order: 3,
      search_terms: [
        { term: 'Eastchester / Edenwald / Baychester', type: 'display_part' },
      ],
    });
    const customResponse: NeighborhoodSelectorResponse = {
      market: 'nyc',
      total_items: 3,
      boroughs: [
        {
          borough: 'Bronx',
          item_count: 3,
          items: [belmont, greenwichVillage, eastchester],
        },
      ],
    };
    const customItems = customResponse.boroughs.flatMap((borough) => borough.items);

    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: customResponse,
      isLoading: false,
      isError: false,
      allItems: customItems,
      itemByKey: new Map(customItems.map((item) => [item.display_key, item])),
      boroughs: ['Bronx'],
    } as ReturnType<typeof useNeighborhoodSelectorData>);

    renderSelector();

    const shortChip = screen.getByTestId('neighborhood-chip-belmont');
    expect(shortChip).not.toHaveClass('col-span-2');
    expect(shortChip).toHaveClass('h-11');
    expect(shortChip).toHaveClass('whitespace-nowrap');

    const longChip = screen.getByTestId('neighborhood-chip-greenwich-village');
    expect(longChip).toHaveClass('col-span-2');
    expect(longChip).toHaveClass('h-11');
    expect(longChip).toHaveClass('whitespace-nowrap');
    expect(longChip).not.toHaveClass('whitespace-normal');

    const veryLongChip = screen.getByTestId('neighborhood-chip-eastchester');
    expect(veryLongChip).toHaveClass('col-span-2');
    expect(veryLongChip).toHaveClass('whitespace-normal');
    expect(veryLongChip).toHaveClass('break-words');
    expect(veryLongChip).not.toHaveClass('h-11');
  });

  it('renders collapsed borough headers according to the A-Team count rules', async () => {
    renderSelector({ defaultValue: ['marble'] });
    const user = userEvent.setup();

    const brooklynHeader = screen.getByTestId('neighborhood-borough-brooklyn');
    const bronxHeader = screen.getByTestId('neighborhood-borough-bronx');

    expect(brooklynHeader).toHaveTextContent('Brooklyn');
    expect(within(brooklynHeader).queryByText('(0)')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('neighborhood-borough-manhattan'));

    expect(bronxHeader).toHaveAttribute('aria-expanded', 'false');
    expect(bronxHeader).toHaveTextContent('Bronx');
    expect(within(bronxHeader).getByText('(1)')).toBeInTheDocument();
    expect(within(bronxHeader).queryByText(/selected/i)).not.toBeInTheDocument();

    const bronxSection = bronxHeader.closest('section');
    expect(bronxSection).not.toBeNull();
    expect(
      within(bronxSection as HTMLElement).queryByRole('button', { name: 'Select all' }),
    ).not.toBeInTheDocument();
    expect(
      within(bronxSection as HTMLElement).queryByRole('button', { name: 'Clear all' }),
    ).not.toBeInTheDocument();
  });

  it('syncs hover state between chips and the map', async () => {
    render(<NeighborhoodSelector showMap value={[]} />);
    const user = userEvent.setup();

    await user.hover(screen.getByTestId('neighborhood-chip-ues'));
    expect(screen.getByTestId('map-hovered')).toHaveTextContent('ues');

    await user.click(screen.getByRole('button', { name: 'Hover Map UES' }));
    expect(screen.getByTestId('neighborhood-chip-ues')).toHaveClass('ring-2');
  });

  it('disables polygon data fetching when the map is hidden', () => {
    renderSelector({ showMap: false });

    expect(useNeighborhoodPolygonsMock).toHaveBeenCalledWith('nyc', false);
    expect(screen.queryByTestId('selector-map')).not.toBeInTheDocument();
  });

  it('shows the map by default and passes a null feature collection when polygon data is unavailable', () => {
    useNeighborhoodPolygonsMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useNeighborhoodPolygons>);

    render(<NeighborhoodSelector value={[]} />);

    expect(useNeighborhoodPolygonsMock).toHaveBeenCalledWith('nyc', true);
    expect(screen.getByTestId('selector-map')).toBeInTheDocument();
    expect(screen.getByTestId('map-feature-collection')).toHaveTextContent('null');
  });

  it('renders selector loading and error states', () => {
    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      allItems: [],
      itemByKey: new Map(),
      boroughs: [],
    } as unknown as ReturnType<typeof useNeighborhoodSelectorData>);
    const { rerender } = renderSelector();

    expect(screen.getByText('Loading neighborhoods…')).toBeInTheDocument();

    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      allItems: [],
      itemByKey: new Map(),
      boroughs: [],
    } as unknown as ReturnType<typeof useNeighborhoodSelectorData>);
    rerender(<NeighborhoodSelector showMap={false} />);

    expect(screen.getByText('Unable to load neighborhoods right now.')).toBeInTheDocument();
  });

  it('renders map loading and error states when the map is shown', () => {
    useNeighborhoodPolygonsMock.mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useNeighborhoodPolygons>);
    const { rerender } = render(<NeighborhoodSelector showMap value={[]} />);

    expect(screen.getByText('Loading map…')).toBeInTheDocument();

    useNeighborhoodPolygonsMock.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useNeighborhoodPolygons>);
    rerender(<NeighborhoodSelector showMap value={[]} />);

    expect(
      screen.getByText('Unable to load neighborhood polygons right now.'),
    ).toBeInTheDocument();
  });

  it('waits to emit a controlled selection until selector items exist and avoids duplicate emissions', () => {
    const onSelectionChange = jest.fn();
    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: { market: 'nyc', total_items: 0, boroughs: [] },
      isLoading: false,
      isError: false,
      allItems: [],
      itemByKey: new Map(),
      boroughs: [],
    } as unknown as ReturnType<typeof useNeighborhoodSelectorData>);

    const { rerender } = renderSelector({
      value: ['ues'],
      onSelectionChange,
    });

    expect(onSelectionChange).not.toHaveBeenCalled();

    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: selectorResponse,
      isLoading: false,
      isError: false,
      allItems,
      itemByKey,
      boroughs,
    } as ReturnType<typeof useNeighborhoodSelectorData>);
    rerender(
      <NeighborhoodSelector
        showMap={false}
        value={['ues']}
        onSelectionChange={onSelectionChange}
      />,
    );

    expect(onSelectionChange).toHaveBeenCalledTimes(1);
    expect(onSelectionChange).toHaveBeenCalledWith(['ues'], [itemByKey.get('ues')]);

    rerender(
      <NeighborhoodSelector
        showMap={false}
        value={['ues']}
        onSelectionChange={onSelectionChange}
      />,
    );

    expect(onSelectionChange).toHaveBeenCalledTimes(1);
  });

  it('filters missing items out of emitted selection payloads during controlled updates', async () => {
    const onSelectionChange = jest.fn();
    const user = userEvent.setup();

    function ControlledHarness() {
      const [value, setValue] = React.useState<string[]>(['missing-key']);

      return (
        <NeighborhoodSelector
          showMap={false}
          value={value}
          onSelectionChange={(keys, items) => {
            onSelectionChange(keys, items);
            setValue(keys);
          }}
        />
      );
    }

    render(<ControlledHarness />);

    await user.click(screen.getByTestId('neighborhood-chip-ues'));

    await waitFor(() => {
      expect(onSelectionChange).toHaveBeenLastCalledWith(
        ['missing-key', 'ues'],
        [itemByKey.get('ues')],
      );
    });
  });

  it('normalizes apostrophes in search text', async () => {
    renderSelector();
    const user = userEvent.setup();

    await user.type(screen.getByTestId('neighborhood-search-input'), 'princes bay');

    const statenIslandSection = screen.getByTestId('neighborhood-borough-staten-island').closest('section');
    expect(statenIslandSection).not.toBeNull();
    expect(
      within(statenIslandSection as HTMLElement).getByText("Prince's Bay"),
    ).toBeInTheDocument();
  });

  it('sorts matched items by rank, then display order, then display name', async () => {
    const eastHarlem = makeItem({
      borough: 'Manhattan',
      display_key: 'east-harlem',
      display_name: 'East Harlem',
      display_order: 2,
      search_terms: [{ term: 'East Harlem', type: 'display_part' }],
    });
    const eastVillage = makeItem({
      borough: 'Manhattan',
      display_key: 'east-village',
      display_name: 'East Village',
      display_order: 2,
      search_terms: [{ term: 'East Village', type: 'display_part' }],
    });
    const upperEastSide = makeItem({
      borough: 'Manhattan',
      display_key: 'upper-east-side',
      display_name: 'Upper East Side',
      display_order: 3,
      search_terms: [{ term: 'Upper East Side', type: 'display_part' }],
    });
    const rankedResponse: NeighborhoodSelectorResponse = {
      market: 'nyc',
      total_items: 3,
      boroughs: [
        {
          borough: 'Manhattan',
          item_count: 3,
          items: [upperEastSide, eastVillage, eastHarlem],
        },
      ],
    };
    const rankedItems = rankedResponse.boroughs.flatMap((borough) => borough.items);
    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: rankedResponse,
      isLoading: false,
      isError: false,
      allItems: rankedItems,
      itemByKey: new Map(rankedItems.map((item) => [item.display_key, item])),
      boroughs: ['Manhattan'],
    } as ReturnType<typeof useNeighborhoodSelectorData>);

    renderSelector();
    const user = userEvent.setup();

    await user.type(screen.getByTestId('neighborhood-search-input'), 'east');

    const manhattanSection = screen
      .getByTestId('neighborhood-borough-manhattan')
      .closest('section');
    expect(manhattanSection).not.toBeNull();

    const chips = within(manhattanSection as HTMLElement)
      .getAllByRole('button')
      .filter((button) => button.dataset['testid']?.startsWith('neighborhood-chip-'));

    expect(chips.map((chip) => chip.dataset['testid'])).toEqual([
      'neighborhood-chip-east-harlem',
      'neighborhood-chip-east-village',
      'neighborhood-chip-upper-east-side',
    ]);
  });

  it('searches safely when an item omits additional boroughs', async () => {
    const astoria = {
      ...makeItem({
        borough: 'Queens',
        display_key: 'astoria',
        display_name: 'Astoria',
        display_order: 1,
        search_terms: [{ term: 'Astoria', type: 'display_part' }],
      }),
      additional_boroughs: undefined,
    } as unknown as SelectorDisplayItem;
    const customResponse: NeighborhoodSelectorResponse = {
      market: 'nyc',
      total_items: 1,
      boroughs: [
        {
          borough: 'Queens',
          item_count: 1,
          items: [astoria],
        },
      ],
    };

    useNeighborhoodSelectorDataMock.mockReturnValue({
      data: customResponse,
      isLoading: false,
      isError: false,
      allItems: [astoria],
      itemByKey: new Map([[astoria.display_key, astoria]]),
      boroughs: ['Queens'],
    } as ReturnType<typeof useNeighborhoodSelectorData>);

    renderSelector();
    const user = userEvent.setup();

    await user.type(screen.getByTestId('neighborhood-search-input'), 'astoria');

    expect(screen.getByTestId('neighborhood-chip-astoria')).toBeInTheDocument();
  });
});
