import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

import { MoreFiltersModal } from '../MoreFiltersModal';
import {
  type ContentFilterSelections,
  DEFAULT_FILTERS,
  type FilterState,
  type TaxonomyContentFilterDefinition,
} from '../../filterTypes';

const TAXONOMY_CONTENT_FILTERS: TaxonomyContentFilterDefinition[] = [
  {
    key: 'goal',
    label: 'Goal',
    filter_type: 'multi_select',
    options: [
      { value: 'enrichment', label: 'Enrichment' },
      { value: 'competition', label: 'Competition' },
    ],
  },
  {
    key: 'style',
    label: 'Style',
    filter_type: 'multi_select',
    options: [
      { value: 'classical', label: 'Classical' },
      { value: 'jazz', label: 'Jazz' },
    ],
  },
];

describe('MoreFiltersModal', () => {
  const onClose = jest.fn();
  const onFiltersChange = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns null when isOpen is false', () => {
    const { container } = render(
      <MoreFiltersModal
        isOpen={false}
        onClose={onClose}
        filters={DEFAULT_FILTERS}
        onFiltersChange={onFiltersChange}
      />
    );

    expect(container.innerHTML).toBe('');
  });

  it('renders modal content when isOpen is true', () => {
    render(
      <MoreFiltersModal
        isOpen={true}
        onClose={onClose}
        filters={DEFAULT_FILTERS}
        onFiltersChange={onFiltersChange}
      />
    );

    expect(screen.getByRole('dialog', { name: /more filters/i })).toBeInTheDocument();
    expect(screen.getByText('Duration')).toBeInTheDocument();
    expect(screen.getByText('Skill Level')).toBeInTheDocument();
  });

  it('skips suggested content filters when the filter key is already populated (continue branch)', async () => {
    const user = userEvent.setup();
    // Pre-populate the 'goal' filter so suggested values for 'goal' are skipped
    const filtersWithGoal: FilterState = {
      ...DEFAULT_FILTERS,
      contentFilters: { goal: ['enrichment'] },
    };

    const suggestedContentFilters: ContentFilterSelections = {
      goal: ['competition'],  // Should be SKIPPED because 'goal' is already populated
      style: ['jazz'],        // Should be APPLIED because 'style' is not populated
    };

    render(
      <MoreFiltersModal
        isOpen={true}
        onClose={onClose}
        filters={filtersWithGoal}
        onFiltersChange={onFiltersChange}
        taxonomyContentFilters={TAXONOMY_CONTENT_FILTERS}
        suggestedContentFilters={suggestedContentFilters}
      />
    );

    // 'Enrichment' should be checked (from existing filters, not overwritten by suggestion)
    const enrichmentLabel = screen.getByText('Enrichment').closest('label');
    const enrichmentInput = enrichmentLabel?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(enrichmentInput.checked).toBe(true);

    // 'Competition' should NOT be checked (suggestion was skipped because goal was already populated)
    const competitionLabel = screen.getByText('Competition').closest('label');
    const competitionInput = competitionLabel?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(competitionInput.checked).toBe(false);

    // 'Jazz' SHOULD be checked (suggestion applied because style was not populated)
    const jazzLabel = screen.getByText('Jazz').closest('label');
    const jazzInput = jazzLabel?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(jazzInput.checked).toBe(true);

    // Apply and verify
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(onFiltersChange).toHaveBeenCalledTimes(1);
    const appliedFilters = onFiltersChange.mock.calls[0][0] as FilterState;
    expect(appliedFilters.contentFilters['goal']).toEqual(['enrichment']);
    expect(appliedFilters.contentFilters['style']).toEqual(['jazz']);
  });

  it('removes a filter key when all options are unchecked (delete branch)', async () => {
    const user = userEvent.setup();
    // Start with 'goal' having one selected value
    const filtersWithGoal: FilterState = {
      ...DEFAULT_FILTERS,
      contentFilters: { goal: ['enrichment'] },
    };

    render(
      <MoreFiltersModal
        isOpen={true}
        onClose={onClose}
        filters={filtersWithGoal}
        onFiltersChange={onFiltersChange}
        taxonomyContentFilters={TAXONOMY_CONTENT_FILTERS}
      />
    );

    // Verify 'Enrichment' is initially checked
    const enrichmentLabel = screen.getByText('Enrichment').closest('label');
    const enrichmentInput = enrichmentLabel?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(enrichmentInput.checked).toBe(true);

    // Uncheck 'Enrichment' — this should trigger the delete path (nextValues.length === 0)
    await user.click(enrichmentInput);
    expect(enrichmentInput.checked).toBe(false);

    // Apply the changes
    await user.click(screen.getByRole('button', { name: 'Apply' }));
    expect(onFiltersChange).toHaveBeenCalledTimes(1);
    const appliedFilters = onFiltersChange.mock.calls[0][0] as FilterState;
    // The 'goal' key should be deleted from contentFilters
    expect(appliedFilters.contentFilters['goal']).toBeUndefined();
  });

  it('enforces single_select taxonomy filters', async () => {
    const user = userEvent.setup();
    const singleSelectFilters: TaxonomyContentFilterDefinition[] = [
      {
        key: 'format',
        label: 'Format',
        filter_type: 'single_select',
        options: [
          { value: 'one_on_one', label: 'One-on-One' },
          { value: 'small_group', label: 'Small Group' },
        ],
      },
    ];

    render(
      <MoreFiltersModal
        isOpen={true}
        onClose={onClose}
        filters={DEFAULT_FILTERS}
        onFiltersChange={onFiltersChange}
        taxonomyContentFilters={singleSelectFilters}
      />
    );

    await user.click(screen.getByText('One-on-One'));
    await user.click(screen.getByText('Small Group'));
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    const appliedFilters = onFiltersChange.mock.calls[0][0] as FilterState;
    expect(appliedFilters.contentFilters['format']).toEqual(['small_group']);
  });

  it('clears all filters when Clear All is clicked', async () => {
    const user = userEvent.setup();
    const filtersWithValues: FilterState = {
      ...DEFAULT_FILTERS,
      duration: [30],
      skillLevel: ['beginner'],
      contentFilters: { goal: ['enrichment'] },
      minRating: '4',
    };

    render(
      <MoreFiltersModal
        isOpen={true}
        onClose={onClose}
        filters={filtersWithValues}
        onFiltersChange={onFiltersChange}
        taxonomyContentFilters={TAXONOMY_CONTENT_FILTERS}
      />
    );

    await user.click(screen.getByRole('button', { name: /clear all/i }));

    expect(onFiltersChange).toHaveBeenCalledTimes(1);
    const clearedFilters = onFiltersChange.mock.calls[0][0] as FilterState;
    expect(clearedFilters.duration).toEqual([]);
    expect(clearedFilters.skillLevel).toEqual([]);
    expect(clearedFilters.contentFilters).toEqual({});
    expect(clearedFilters.minRating).toBe('any');
    expect(onClose).toHaveBeenCalled();
  });

  it('does not apply suggested values that are not in the allowed options', () => {
    const suggestedContentFilters: ContentFilterSelections = {
      goal: ['nonexistent_value'],
    };

    render(
      <MoreFiltersModal
        isOpen={true}
        onClose={onClose}
        filters={DEFAULT_FILTERS}
        onFiltersChange={onFiltersChange}
        taxonomyContentFilters={TAXONOMY_CONTENT_FILTERS}
        suggestedContentFilters={suggestedContentFilters}
      />
    );

    // Both goal options should be unchecked since 'nonexistent_value' is not in allowed options
    const enrichmentLabel = screen.getByText('Enrichment').closest('label');
    const enrichmentInput = enrichmentLabel?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(enrichmentInput.checked).toBe(false);

    const competitionLabel = screen.getByText('Competition').closest('label');
    const competitionInput = competitionLabel?.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(competitionInput.checked).toBe(false);
  });
});
