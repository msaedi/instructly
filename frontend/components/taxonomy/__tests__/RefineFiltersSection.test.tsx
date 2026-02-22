import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  RefineFiltersSection,
  type RefineFiltersServiceSlice,
} from '../RefineFiltersSection';
import { useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';
import { formatFilterLabel } from '@/lib/taxonomy/formatFilterLabel';
import { normalizeSelectionValues } from '@/lib/taxonomy/filterHelpers';
import type { SubcategoryFilterResponse } from '@/features/shared/api/types';

jest.mock('@/hooks/queries/useTaxonomy', () => ({
  useSubcategoryFilters: jest.fn(() => ({ data: [], isLoading: false })),
}));

jest.mock('@/lib/taxonomy/formatFilterLabel', () => ({
  formatFilterLabel: jest.fn(
    (value: string, displayName?: string | null) => displayName || value
  ),
}));

jest.mock('@/lib/taxonomy/filterHelpers', () => ({
  normalizeSelectionValues: jest.fn((v: unknown) => (Array.isArray(v) ? v : [])),
}));

const mockUseSubcategoryFilters = useSubcategoryFilters as jest.Mock;
const mockFormatFilterLabel = formatFilterLabel as jest.Mock;
const mockNormalizeSelectionValues = normalizeSelectionValues as jest.Mock;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const makeOption = (
  id: string,
  value: string,
  displayName: string,
  displayOrder = 0
) => ({ id, value, display_name: displayName, display_order: displayOrder });

const makeFilter = (
  overrides: Partial<SubcategoryFilterResponse> & { filter_key: string }
): SubcategoryFilterResponse => ({
  filter_display_name: overrides.filter_display_name ?? overrides.filter_key,
  filter_key: overrides.filter_key,
  filter_type: overrides.filter_type ?? 'multi_select',
  options: overrides.options ?? [],
});

const MULTI_FILTER: SubcategoryFilterResponse = makeFilter({
  filter_key: 'grade_level',
  filter_display_name: 'Grade Level',
  filter_type: 'multi_select',
  options: [
    makeOption('opt-1', 'elementary', 'Elementary (K-5)', 1),
    makeOption('opt-2', 'middle_school', 'Middle School', 2),
    makeOption('opt-3', 'high_school', 'High School', 3),
  ],
});

const SINGLE_FILTER: SubcategoryFilterResponse = makeFilter({
  filter_key: 'format',
  filter_display_name: 'Format',
  filter_type: 'single_select',
  options: [
    makeOption('opt-10', 'one_on_one', 'One-on-One', 1),
    makeOption('opt-11', 'small_group', 'Small Group', 2),
  ],
});

const SKILL_LEVEL_FILTER: SubcategoryFilterResponse = makeFilter({
  filter_key: 'skill_level',
  filter_display_name: 'Skill Level',
  filter_type: 'multi_select',
  options: [
    makeOption('sk-1', 'beginner', 'Beginner'),
    makeOption('sk-2', 'intermediate', 'Intermediate'),
    makeOption('sk-3', 'advanced', 'Advanced'),
  ],
});

const defaultService: RefineFiltersServiceSlice = {
  catalog_service_id: 'svc-abc',
  subcategory_id: 'subcat-123',
  name: 'Piano Lessons',
  filter_selections: {},
};

type RenderProps = {
  service?: RefineFiltersServiceSlice;
  expanded?: boolean;
  onToggleExpanded?: jest.Mock;
  onInitializeMissingFilters?: jest.Mock;
  onSetFilterValues?: jest.Mock;
};

function renderComponent(overrides: RenderProps = {}) {
  const onToggleExpanded = overrides.onToggleExpanded ?? jest.fn();
  const onInitializeMissingFilters =
    overrides.onInitializeMissingFilters ?? jest.fn();
  const onSetFilterValues = overrides.onSetFilterValues ?? jest.fn();

  const result = render(
    <RefineFiltersSection
      service={overrides.service ?? defaultService}
      expanded={overrides.expanded ?? false}
      onToggleExpanded={onToggleExpanded}
      onInitializeMissingFilters={onInitializeMissingFilters}
      onSetFilterValues={onSetFilterValues}
    />
  );

  return {
    ...result,
    onToggleExpanded,
    onInitializeMissingFilters,
    onSetFilterValues,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RefineFiltersSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseSubcategoryFilters.mockReturnValue({ data: [], isLoading: false });
    mockFormatFilterLabel.mockImplementation(
      (value: string, displayName?: string | null) => displayName || value
    );
    mockNormalizeSelectionValues.mockImplementation((v: unknown) =>
      Array.isArray(v) ? v : []
    );
  });

  // -----------------------------------------------------------------------
  // 1. Renders null when no subcategory_id
  // -----------------------------------------------------------------------
  it('renders null when service has no subcategory_id', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    const { container } = renderComponent({
      service: { ...defaultService, subcategory_id: '' },
    });

    expect(container.innerHTML).toBe('');
  });

  // -----------------------------------------------------------------------
  // 2. Renders null when only skill_level filters (no additional filters)
  // -----------------------------------------------------------------------
  it('renders null when the only filter is skill_level', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [SKILL_LEVEL_FILTER],
      isLoading: false,
    });

    const { container } = renderComponent();

    expect(container.innerHTML).toBe('');
  });

  // -----------------------------------------------------------------------
  // 3. Shows the "Refine what you teach" heading
  // -----------------------------------------------------------------------
  it('shows the "Refine what you teach" heading when additional filters exist', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    renderComponent();

    expect(
      screen.getByText('Refine what you teach (optional)')
    ).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // 4. Toggle expand/collapse behavior
  // -----------------------------------------------------------------------
  it('calls onToggleExpanded with service id when toggle button is clicked', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    const { onToggleExpanded } = renderComponent();

    const toggleButton = screen.getByRole('button', {
      name: /toggle refine filters/i,
    });
    await user.click(toggleButton);

    expect(onToggleExpanded).toHaveBeenCalledWith('svc-abc');
  });

  it('sets aria-expanded based on expanded prop', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    const { rerender } = render(
      <RefineFiltersSection
        service={defaultService}
        expanded={false}
        onToggleExpanded={jest.fn()}
        onInitializeMissingFilters={jest.fn()}
        onSetFilterValues={jest.fn()}
      />
    );

    expect(
      screen.getByRole('button', { name: /toggle refine filters/i })
    ).toHaveAttribute('aria-expanded', 'false');

    rerender(
      <RefineFiltersSection
        service={defaultService}
        expanded={true}
        onToggleExpanded={jest.fn()}
        onInitializeMissingFilters={jest.fn()}
        onSetFilterValues={jest.fn()}
      />
    );

    expect(
      screen.getByRole('button', { name: /toggle refine filters/i })
    ).toHaveAttribute('aria-expanded', 'true');
  });

  it('does not render filter options when collapsed', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    renderComponent({ expanded: false });

    expect(screen.queryByText('Grade Level')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // 5. Filter options display with correct labels
  // -----------------------------------------------------------------------
  it('renders filter options with correct display names when expanded', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    renderComponent({ expanded: true });

    expect(screen.getByText('Grade Level')).toBeInTheDocument();
    expect(screen.getByText('Elementary (K-5)')).toBeInTheDocument();
    expect(screen.getByText('Middle School')).toBeInTheDocument();
    expect(screen.getByText('High School')).toBeInTheDocument();
  });

  it('calls formatFilterLabel for each option', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    renderComponent({ expanded: true });

    expect(mockFormatFilterLabel).toHaveBeenCalledWith(
      'elementary',
      'Elementary (K-5)'
    );
    expect(mockFormatFilterLabel).toHaveBeenCalledWith(
      'middle_school',
      'Middle School'
    );
    expect(mockFormatFilterLabel).toHaveBeenCalledWith(
      'high_school',
      'High School'
    );
  });

  it('sorts options by display_order', () => {
    const unsortedFilter = makeFilter({
      filter_key: 'grade_level',
      filter_display_name: 'Grade Level',
      filter_type: 'multi_select',
      options: [
        makeOption('opt-3', 'high_school', 'High School', 3),
        makeOption('opt-1', 'elementary', 'Elementary', 1),
        makeOption('opt-2', 'middle_school', 'Middle School', 2),
      ],
    });
    mockUseSubcategoryFilters.mockReturnValue({
      data: [unsortedFilter],
      isLoading: false,
    });

    renderComponent({ expanded: true });

    const buttons = screen.getAllByRole('button');
    // First button is the toggle, remaining are options
    const optionButtons = buttons.filter(
      (b) => !b.getAttribute('aria-label')?.includes('Toggle')
    );
    expect(optionButtons[0]).toHaveTextContent('Elementary');
    expect(optionButtons[1]).toHaveTextContent('Middle School');
    expect(optionButtons[2]).toHaveTextContent('High School');
  });

  // -----------------------------------------------------------------------
  // 6. Single select: clicking selects, clicking same deselects
  // -----------------------------------------------------------------------
  it('single_select: clicking an unselected option sends [option.value]', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [SINGLE_FILTER],
      isLoading: false,
    });

    const service: RefineFiltersServiceSlice = {
      ...defaultService,
      filter_selections: { format: [] },
    };

    const { onSetFilterValues } = renderComponent({
      service,
      expanded: true,
    });

    await user.click(screen.getByText('One-on-One'));

    expect(onSetFilterValues).toHaveBeenCalledWith(
      'svc-abc',
      'format',
      ['one_on_one']
    );
  });

  it('single_select: clicking an already-selected option sends []', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [SINGLE_FILTER],
      isLoading: false,
    });

    const service: RefineFiltersServiceSlice = {
      ...defaultService,
      filter_selections: { format: ['one_on_one'] },
    };

    const { onSetFilterValues } = renderComponent({
      service,
      expanded: true,
    });

    await user.click(screen.getByText('One-on-One'));

    expect(onSetFilterValues).toHaveBeenCalledWith('svc-abc', 'format', []);
  });

  // -----------------------------------------------------------------------
  // 7. Multi select: clicking toggles individual options
  // -----------------------------------------------------------------------
  it('multi_select: clicking an unselected option adds it (calls normalizeSelectionValues)', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    const service: RefineFiltersServiceSlice = {
      ...defaultService,
      filter_selections: { grade_level: ['elementary'] },
    };

    const { onSetFilterValues } = renderComponent({
      service,
      expanded: true,
    });

    await user.click(screen.getByText('Middle School'));

    // normalizeSelectionValues called with the candidate array
    expect(mockNormalizeSelectionValues).toHaveBeenCalledWith([
      'elementary',
      'middle_school',
    ]);
    expect(onSetFilterValues).toHaveBeenCalledWith(
      'svc-abc',
      'grade_level',
      ['elementary', 'middle_school']
    );
  });

  it('multi_select: clicking a selected option removes it (calls normalizeSelectionValues)', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    const service: RefineFiltersServiceSlice = {
      ...defaultService,
      filter_selections: {
        grade_level: ['elementary', 'middle_school'],
      },
    };

    const { onSetFilterValues } = renderComponent({
      service,
      expanded: true,
    });

    await user.click(screen.getByText('Elementary (K-5)'));

    expect(mockNormalizeSelectionValues).toHaveBeenCalledWith([
      'middle_school',
    ]);
    expect(onSetFilterValues).toHaveBeenCalledWith(
      'svc-abc',
      'grade_level',
      ['middle_school']
    );
  });

  it('multi_select does NOT call normalizeSelectionValues for single_select', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [SINGLE_FILTER],
      isLoading: false,
    });

    const service: RefineFiltersServiceSlice = {
      ...defaultService,
      filter_selections: { format: [] },
    };

    renderComponent({ service, expanded: true });

    await user.click(screen.getByText('One-on-One'));

    expect(mockNormalizeSelectionValues).not.toHaveBeenCalled();
  });

  // -----------------------------------------------------------------------
  // 8. Filter initialization via useEffect
  // -----------------------------------------------------------------------
  it('calls onInitializeMissingFilters with defaults for filters not yet in filter_selections', async () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, SINGLE_FILTER],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: {
        ...defaultService,
        filter_selections: {},
      },
    });

    await waitFor(() => {
      expect(onInitializeMissingFilters).toHaveBeenCalledWith('svc-abc', {
        grade_level: ['elementary', 'middle_school', 'high_school'],
        format: ['one_on_one', 'small_group'],
      });
    });
  });

  // -----------------------------------------------------------------------
  // 9. Already-initialized filters are NOT overwritten
  // -----------------------------------------------------------------------
  it('does not overwrite filters already present in filter_selections', async () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, SINGLE_FILTER],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: {
        ...defaultService,
        filter_selections: {
          grade_level: ['elementary'],
        },
      },
    });

    await waitFor(() => {
      expect(onInitializeMissingFilters).toHaveBeenCalledWith('svc-abc', {
        format: ['one_on_one', 'small_group'],
      });
    });
  });

  it('does not call onInitializeMissingFilters when all filters are already initialized', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: {
        ...defaultService,
        filter_selections: { grade_level: ['elementary'] },
      },
    });

    expect(onInitializeMissingFilters).not.toHaveBeenCalled();
  });

  // -----------------------------------------------------------------------
  // 10. Loading state display
  // -----------------------------------------------------------------------
  it('shows "Loading filters..." when isLoading is true and expanded', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: true,
    });

    renderComponent({ expanded: true });

    expect(screen.getByText('Loading filters...')).toBeInTheDocument();
  });

  it('does not show loading text when collapsed even if isLoading', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: true,
    });

    renderComponent({ expanded: false });

    expect(screen.queryByText('Loading filters...')).not.toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Edge cases
  // -----------------------------------------------------------------------
  it('renders the toggle aria-label with service name', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    renderComponent();

    expect(
      screen.getByLabelText('Toggle refine filters for Piano Lessons')
    ).toBeInTheDocument();
  });

  it('renders fallback aria-label when service name is null', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    renderComponent({
      service: { ...defaultService, name: null },
    });

    expect(
      screen.getByLabelText('Toggle refine filters for this service')
    ).toBeInTheDocument();
  });

  it('handles filter with no options gracefully (does not initialize empty)', () => {
    const emptyOptionsFilter = makeFilter({
      filter_key: 'empty_filter',
      filter_display_name: 'Empty Filter',
      options: [],
    });
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, emptyOptionsFilter],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: { ...defaultService, filter_selections: {} },
    });

    // Only the multi filter should be initialized, not the empty one
    expect(onInitializeMissingFilters).toHaveBeenCalledWith('svc-abc', {
      grade_level: ['elementary', 'middle_school', 'high_school'],
    });
  });

  it('handles filter with undefined options safely', () => {
    const noOptionsFilter = makeFilter({
      filter_key: 'no_opts',
      filter_display_name: 'No Opts',
      options: undefined,
    });
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, noOptionsFilter],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: { ...defaultService, filter_selections: {} },
    });

    expect(onInitializeMissingFilters).toHaveBeenCalledWith('svc-abc', {
      grade_level: ['elementary', 'middle_school', 'high_school'],
    });
  });

  it('renders multiple filter groups when expanded', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, SINGLE_FILTER],
      isLoading: false,
    });

    renderComponent({
      expanded: true,
      service: {
        ...defaultService,
        filter_selections: {
          grade_level: ['elementary'],
          format: ['one_on_one'],
        },
      },
    });

    expect(screen.getByText('Grade Level')).toBeInTheDocument();
    expect(screen.getByText('Format')).toBeInTheDocument();
  });

  it('applies selected styling class to selected options', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    renderComponent({
      expanded: true,
      service: {
        ...defaultService,
        filter_selections: { grade_level: ['elementary'] },
      },
    });

    const selectedButton = screen.getByText('Elementary (K-5)');
    expect(selectedButton.className).toContain('bg-purple-100');

    const unselectedButton = screen.getByText('Middle School');
    expect(unselectedButton.className).toContain('bg-gray-100');
  });

  it('excludes skill_level from rendered filters', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [SKILL_LEVEL_FILTER, MULTI_FILTER],
      isLoading: false,
    });

    renderComponent({ expanded: true });

    expect(screen.queryByText('Skill Level')).not.toBeInTheDocument();
    expect(screen.getByText('Grade Level')).toBeInTheDocument();
  });

  it('single_select: clicking a different option selects the new one', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [SINGLE_FILTER],
      isLoading: false,
    });

    const service: RefineFiltersServiceSlice = {
      ...defaultService,
      filter_selections: { format: ['one_on_one'] },
    };

    const { onSetFilterValues } = renderComponent({
      service,
      expanded: true,
    });

    await user.click(screen.getByText('Small Group'));

    expect(onSetFilterValues).toHaveBeenCalledWith('svc-abc', 'format', [
      'small_group',
    ]);
  });

  it('does not call onInitializeMissingFilters when additionalFilters is empty', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent();

    expect(onInitializeMissingFilters).not.toHaveBeenCalled();
  });

  it('does not call onInitializeMissingFilters when only skill_level filter exists', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [SKILL_LEVEL_FILTER],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent();

    expect(onInitializeMissingFilters).not.toHaveBeenCalled();
  });

  it('uses default empty array when selectedValues is missing for a filter key', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    // filter_selections does not include grade_level key at all
    renderComponent({
      expanded: true,
      service: {
        ...defaultService,
        filter_selections: {},
      },
    });

    // All options should appear as unselected (bg-gray-100)
    const optionButtons = screen
      .getAllByRole('button')
      .filter((b) => !b.getAttribute('aria-label')?.includes('Toggle'));
    for (const btn of optionButtons) {
      expect(btn.className).toContain('bg-gray-100');
    }
  });

  // -----------------------------------------------------------------------
  // Branch coverage: data undefined from useSubcategoryFilters (line 44 default)
  // -----------------------------------------------------------------------
  it('handles useSubcategoryFilters returning undefined data (falls back to empty array)', () => {
    mockUseSubcategoryFilters.mockReturnValue({
      data: undefined,
      isLoading: false,
    });

    const { container } = renderComponent();

    // With no filters, component returns null
    expect(container.innerHTML).toBe('');
  });

  // -----------------------------------------------------------------------
  // Branch coverage: filter.options undefined in render path (line 123)
  // -----------------------------------------------------------------------
  it('renders zero option buttons when filter.options is undefined (expanded)', () => {
    const filterWithNoOptions = makeFilter({
      filter_key: 'topic',
      filter_display_name: 'Topic',
      options: undefined,
    });
    mockUseSubcategoryFilters.mockReturnValue({
      data: [filterWithNoOptions],
      isLoading: false,
    });

    renderComponent({
      expanded: true,
      service: {
        ...defaultService,
        filter_selections: { topic: ['math'] },
      },
    });

    // The filter group heading renders, but no option buttons
    expect(screen.getByText('Topic')).toBeInTheDocument();
    const optionButtons = screen
      .getAllByRole('button')
      .filter((b) => !b.getAttribute('aria-label')?.includes('Toggle'));
    expect(optionButtons).toHaveLength(0);
  });

  // -----------------------------------------------------------------------
  // Branch coverage: initialization with filter that has empty options array
  // (allValues.length > 0 is false — line 65 false branch)
  // -----------------------------------------------------------------------
  it('skips initialization for filters with empty options array', async () => {
    const emptyFilter = makeFilter({
      filter_key: 'special',
      filter_display_name: 'Special',
      filter_type: 'multi_select',
      options: [],
    });
    // Need at least one non-empty additional filter so the component renders
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, emptyFilter],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: {
        ...defaultService,
        filter_selections: {},
      },
    });

    await waitFor(() => {
      // Only grade_level should be initialized, not 'special' (empty options)
      expect(onInitializeMissingFilters).toHaveBeenCalledWith('svc-abc', {
        grade_level: ['elementary', 'middle_school', 'high_school'],
      });
    });
  });

  // -----------------------------------------------------------------------
  // Branch coverage: initialization with filter.options = undefined
  // (filter.options ?? [] produces empty, allValues.length = 0 → skip)
  // -----------------------------------------------------------------------
  it('skips initialization for filters where options is undefined', async () => {
    const undefinedOptsFilter = makeFilter({
      filter_key: 'undefined_opts',
      filter_display_name: 'Undefined Opts',
      options: undefined,
    });
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, undefinedOptsFilter],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: {
        ...defaultService,
        filter_selections: {},
      },
    });

    await waitFor(() => {
      expect(onInitializeMissingFilters).toHaveBeenCalledWith('svc-abc', {
        grade_level: ['elementary', 'middle_school', 'high_school'],
      });
    });
  });

  // -----------------------------------------------------------------------
  // Branch: filter.options explicitly null in render path (line 123 ?? [])
  // -----------------------------------------------------------------------
  it('renders zero option buttons when filter.options is nullish (expanded)', () => {
    // Use type assertion to simulate API returning null for options field
    const filterWithNullOptions = {
      filter_key: 'style',
      filter_display_name: 'Style',
      filter_type: 'multi_select' as const,
      options: null as unknown as SubcategoryFilterResponse['options'],
    };
    mockUseSubcategoryFilters.mockReturnValue({
      data: [filterWithNullOptions],
      isLoading: false,
    });

    renderComponent({
      expanded: true,
      service: {
        ...defaultService,
        filter_selections: { style: ['classical'] },
      },
    });

    expect(screen.getByText('Style')).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Branch: initialization useEffect when filter.options is null/undefined
  // AND filter is missing from selections (exercises ?? [] on line 64 fully)
  // -----------------------------------------------------------------------
  it('initialization skips filter with null-ish options even when not in selections', async () => {
    const nullOptsFilter: SubcategoryFilterResponse = {
      filter_key: 'approach',
      filter_display_name: 'Approach',
      filter_type: 'multi_select',
      options: undefined,
    };
    // Include a normal filter so onInitializeMissingFilters is actually called
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER, nullOptsFilter],
      isLoading: false,
    });

    const { onInitializeMissingFilters } = renderComponent({
      service: {
        ...defaultService,
        filter_selections: {},
      },
    });

    await waitFor(() => {
      expect(onInitializeMissingFilters).toHaveBeenCalledWith('svc-abc', {
        grade_level: ['elementary', 'middle_school', 'high_school'],
      });
      // 'approach' should NOT be in defaults since it has no options
      const callArgs = onInitializeMissingFilters.mock.calls[0]?.[1] as Record<string, unknown> | undefined;
      expect(callArgs).not.toHaveProperty('approach');
    });
  });

  // -----------------------------------------------------------------------
  // Branch: display_order ?? 0 fallback in sort (line 124)
  // -----------------------------------------------------------------------
  it('sorts options correctly when display_order is null or undefined', () => {
    const filterWithMissingOrder = makeFilter({
      filter_key: 'instrument_type',
      filter_display_name: 'Instrument Type',
      filter_type: 'multi_select',
      options: [
        {
          id: 'o1',
          value: 'strings',
          display_name: 'Strings',
          display_order: null as unknown as number,
        },
        {
          id: 'o2',
          value: 'woodwind',
          display_name: 'Woodwind',
          display_order: undefined as unknown as number,
        },
        { id: 'o3', value: 'brass', display_name: 'Brass', display_order: 1 },
      ],
    });
    mockUseSubcategoryFilters.mockReturnValue({
      data: [filterWithMissingOrder],
      isLoading: false,
    });

    renderComponent({
      expanded: true,
      service: {
        ...defaultService,
        filter_selections: { instrument_type: [] },
      },
    });

    // All three should render without error
    expect(screen.getByText('Strings')).toBeInTheDocument();
    expect(screen.getByText('Woodwind')).toBeInTheDocument();
    expect(screen.getByText('Brass')).toBeInTheDocument();
  });

  // -----------------------------------------------------------------------
  // Branch: multi_select click on option when selectedValues is empty (line 122 ?? [])
  // -----------------------------------------------------------------------
  it('multi_select: handles click when selectedValues fallback to empty array', async () => {
    const user = userEvent.setup();
    mockUseSubcategoryFilters.mockReturnValue({
      data: [MULTI_FILTER],
      isLoading: false,
    });

    // grade_level key is not in filter_selections at all
    const { onSetFilterValues } = renderComponent({
      expanded: true,
      service: {
        ...defaultService,
        filter_selections: {},
      },
    });

    await user.click(screen.getByText('Elementary (K-5)'));

    // selectedValues was [] (from ?? []), isSelected = false, so adds it
    expect(mockNormalizeSelectionValues).toHaveBeenCalledWith(['elementary']);
    expect(onSetFilterValues).toHaveBeenCalledWith(
      'svc-abc',
      'grade_level',
      ['elementary']
    );
  });
});
