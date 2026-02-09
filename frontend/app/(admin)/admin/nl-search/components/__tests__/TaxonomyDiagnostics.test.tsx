import { render, screen } from '@testing-library/react';

import { TaxonomyDiagnostics } from '../TaxonomyDiagnostics';
import type { components } from '@/features/shared/api/types';

type SearchMeta = components['schemas']['NLSearchMeta'];

function makeMeta(overrides: Partial<SearchMeta> = {}): SearchMeta {
  return {
    cache_hit: false,
    latency_ms: 123,
    limit: 20,
    parsed: {
      service_query: 'math',
      use_user_location: false,
    },
    parsing_mode: 'regex',
    query: 'ap math',
    total_results: 3,
    ...overrides,
  } as SearchMeta;
}

describe('TaxonomyDiagnostics', () => {
  it('renders inferred filters and available definitions with inferred source', () => {
    const meta = makeMeta({
      inferred_filters: { course_level: ['ap'] },
      effective_subcategory_id: 'sub_math',
      effective_subcategory_name: 'Math',
      available_content_filters: [
        {
          key: 'course_level',
          label: 'Course Level',
          type: 'multi_select',
          options: [
            { value: 'regular', label: 'Regular' },
            { value: 'honors', label: 'Honors' },
            { value: 'ap', label: 'AP' },
          ],
        },
      ],
    });

    render(<TaxonomyDiagnostics meta={meta} />);

    expect(screen.getByText('Inferred Filters')).toBeInTheDocument();
    const inferredLine = screen
      .getAllByText((_, element) => element?.textContent === 'course_level: ap')
      .find((element) => element.tagName === 'LI');
    expect(inferredLine).toBeDefined();
    expect(screen.getByText('Math (ID: sub_math)')).toBeInTheDocument();
    expect(screen.getByText('Source: inferred (top-match consensus)')).toBeInTheDocument();
    expect(screen.getByText('Course Level [multi_select]')).toBeInTheDocument();
    expect(screen.getByText(/regular, honors, ap/)).toBeInTheDocument();
    expect(
      screen.getByText('Hard Filters Applied: none (all inferred filters are soft)')
    ).toBeInTheDocument();
  });

  it('marks effective subcategory source as explicit when subcategory hard filter was applied', () => {
    const meta = makeMeta({
      effective_subcategory_id: 'sub_math',
      effective_subcategory_name: 'Math',
      filters_applied: ['subcategory', 'taxonomy:course_level'],
    });

    render(<TaxonomyDiagnostics meta={meta} />);

    expect(screen.getByText('Source: explicit (URL param)')).toBeInTheDocument();
    expect(
      screen.getByText('Hard Filters Applied: subcategory, taxonomy:course_level')
    ).toBeInTheDocument();
  });

  it('renders empty-state diagnostics when taxonomy metadata is unavailable', () => {
    const meta = makeMeta();
    render(<TaxonomyDiagnostics meta={meta} />);

    expect(screen.getByText('None inferred')).toBeInTheDocument();
    expect(screen.getByText('Effective Subcategory: none')).toBeInTheDocument();
    expect(screen.getByText('Source: none')).toBeInTheDocument();
    expect(screen.getByText('No filter definitions available')).toBeInTheDocument();
  });
});
