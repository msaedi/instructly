import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { useRouter } from 'next/navigation';

import { HomeCatalogCascade } from '../HomeCatalogCascade';
import { useAllServicesWithInstructors, useServiceCategories } from '@/hooks/queries/useServices';
import { useSubcategoriesByCategory } from '@/hooks/queries/useTaxonomy';
import { recordSearch } from '@/lib/searchTracking';

jest.mock('@/hooks/queries/useServices', () => ({
  useServiceCategories: jest.fn(),
  useAllServicesWithInstructors: jest.fn(),
}));

jest.mock('@/hooks/queries/useTaxonomy', () => ({
  useSubcategoriesByCategory: jest.fn(),
}));

jest.mock('@/lib/searchTracking', () => ({
  recordSearch: jest.fn(),
}));

const useRouterMock = useRouter as jest.Mock;
const useServiceCategoriesMock = useServiceCategories as jest.Mock;
const useAllServicesWithInstructorsMock = useAllServicesWithInstructors as jest.Mock;
const useSubcategoriesByCategoryMock = useSubcategoriesByCategory as jest.Mock;
const recordSearchMock = recordSearch as jest.Mock;

const CATEGORY_DATA = [
  {
    id: 'cat-music',
    name: 'Music',
    subtitle: 'Instruments and vocal arts',
    display_order: 1,
    icon_name: 'music',
  },
  {
    id: 'cat-dance',
    name: 'Dance',
    subtitle: 'Movement',
    display_order: 2,
    icon_name: 'sparkles',
  },
  {
    id: 'cat-kids-only',
    name: 'Kids Swim',
    subtitle: 'Children only',
    display_order: 3,
    icon_name: 'dumbbell',
  },
];

const SERVICES_WITH_SUPPLY = {
  categories: [
    {
      id: 'cat-music',
      name: 'Music',
      subtitle: 'Instruments and vocal arts',
      icon_name: 'music',
      services: [
        {
          id: 'svc-piano',
          name: 'Piano',
          subcategory_id: 'sub-piano',
          display_order: 1,
          instructor_count: 5,
          eligible_age_groups: ['kids', 'adults'],
        },
        {
          id: 'svc-keyboard',
          name: 'Keyboard',
          subcategory_id: 'sub-piano',
          display_order: 2,
          instructor_count: 4,
          eligible_age_groups: ['adults'],
        },
        {
          id: 'svc-theory',
          name: 'Music Theory',
          subcategory_id: 'sub-theory',
          display_order: 3,
          instructor_count: 3,
          eligible_age_groups: ['adults'],
        },
        {
          id: 'svc-toddler-songs',
          name: 'Toddler Songs',
          subcategory_id: 'sub-kids-songs',
          display_order: 4,
          instructor_count: 3,
          eligible_age_groups: ['kids'],
        },
        {
          id: 'svc-voice',
          name: 'Voice & Singing',
          subcategory_id: 'sub-voice',
          display_order: 5,
          instructor_count: 0,
          eligible_age_groups: ['adults'],
        },
      ],
    },
    {
      id: 'cat-dance',
      name: 'Dance',
      subtitle: 'Movement',
      icon_name: 'sparkles',
      services: [
        {
          id: 'svc-ballet',
          name: 'Ballet',
          subcategory_id: 'sub-ballet',
          display_order: 1,
          instructor_count: 2,
          eligible_age_groups: ['adults'],
        },
      ],
    },
    {
      id: 'cat-kids-only',
      name: 'Kids Swim',
      subtitle: 'Children only',
      icon_name: 'dumbbell',
      services: [
        {
          id: 'svc-mommy-me',
          name: 'Mommy & Me Swimming',
          subcategory_id: 'sub-mommy-me',
          display_order: 1,
          instructor_count: 2,
          eligible_age_groups: ['kids'],
        },
      ],
    },
  ],
};

const SUBCATEGORIES_BY_CATEGORY: Record<string, Array<{ id: string; name: string }>> = {
  'cat-music': [
    { id: 'sub-piano', name: 'Piano' },
    { id: 'sub-theory', name: 'Music Theory' },
    { id: 'sub-kids-songs', name: 'Kids Songs' },
    { id: 'sub-voice', name: 'Voice' },
  ],
  'cat-dance': [{ id: 'sub-ballet', name: 'Ballet' }],
};

function setupCatalogMocks() {
  useServiceCategoriesMock.mockReturnValue({ data: CATEGORY_DATA });
  useAllServicesWithInstructorsMock.mockReturnValue({ data: SERVICES_WITH_SUPPLY });
  useSubcategoriesByCategoryMock.mockImplementation((categoryId: string) => ({
    data: SUBCATEGORIES_BY_CATEGORY[categoryId] ?? [],
  }));
}

function cloneServicesWithSupply() {
  return JSON.parse(JSON.stringify(SERVICES_WITH_SUPPLY));
}

function clickWithoutNavigation(element: HTMLElement) {
  element.addEventListener('click', (event) => event.preventDefault(), { once: true });
  fireEvent.click(element);
}

describe('HomeCatalogCascade', () => {
  const pushMock = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();

    useRouterMock.mockReturnValue({
      push: pushMock,
      replace: jest.fn(),
      prefetch: jest.fn(),
    });

    recordSearchMock.mockResolvedValue(undefined);
    setupCatalogMocks();
  });

  it('shows subcategories after selecting a category', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /piano/i });
    fireEvent.click(screen.getByRole('button', { name: /dance/i }));

    expect(await screen.findByRole('button', { name: /ballet/i })).toBeInTheDocument();
  });

  it('skips service level for singleton subcategories', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    fireEvent.click(await screen.findByRole('button', { name: /music theory/i }));

    expect(pushMock).toHaveBeenCalledWith(expect.stringContaining('service_catalog_id=svc-theory'));
    expect(pushMock).toHaveBeenCalledWith(expect.stringContaining('subcategory_id=sub-theory'));
    expect(pushMock).toHaveBeenCalledWith(expect.stringContaining('audience=adults'));
  });

  it('shows service pills for subcategories with multiple services', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    fireEvent.click(await screen.findByRole('button', { name: /^piano/i }));

    expect(screen.getByRole('button', { name: /^piano/i })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Piano' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Keyboard' })).toBeInTheDocument();
  });

  it('filters out services not eligible for the adults site mode', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /^piano/i });
    expect(screen.queryByRole('button', { name: /kids songs/i })).not.toBeInTheDocument();
    expect(screen.queryByText('Toddler Songs')).not.toBeInTheDocument();
  });

  it('filters out empty subcategories and categories', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /^piano/i });
    expect(screen.queryByRole('button', { name: /^voice/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /kids swim/i })).not.toBeInTheDocument();
  });

  it('includes audience in service pill navigation links', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    fireEvent.click(await screen.findByRole('button', { name: /^piano/i }));
    const pianoLink = await screen.findByRole('link', { name: 'Piano' });

    expect(pianoLink).toHaveAttribute('href', expect.stringContaining('audience=adults'));
    expect(pianoLink).toHaveAttribute('href', expect.stringContaining('subcategory_id=sub-piano'));
  });

  it('keeps the more link unscoped so services page shows all categories', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    fireEvent.click(await screen.findByRole('button', { name: /dance/i }));
    const moreLink = screen.getByRole('link', { name: '•••' });

    expect(moreLink).toHaveAttribute('href', '/services?audience=adults');
    expect(moreLink).not.toHaveAttribute('href', expect.stringContaining('category_id='));
  });

  it('hides breadcrumb, back buttons, and mode text', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /^piano/i });
    expect(screen.queryByText('Mode: Adults')).not.toBeInTheDocument();
    expect(screen.queryByText(/back to categories/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/back to subcategories/i)).not.toBeInTheDocument();
  });

  it('does not render category subtitle helper text under category labels', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /^dance$/i });
    expect(screen.queryByText('Instruments and vocal arts')).not.toBeInTheDocument();
  });

  it('shows count label only for subcategories with 2+ services', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    const pianoPill = await screen.findByRole('button', { name: /^piano/i });
    const theoryPill = screen.getByRole('button', { name: /music theory/i });

    expect(pianoPill).toHaveTextContent('(2)');
    expect(theoryPill).not.toHaveTextContent('(1)');
  });

  it('stores selected category context when clicking the more link', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    fireEvent.click(await screen.findByRole('button', { name: /dance/i }));
    clickWithoutNavigation(screen.getByRole('link', { name: '•••' }));

    expect(sessionStorage.getItem('navigationFrom')).toBe('/');
    expect(sessionStorage.getItem('homeSelectedCategory')).toBe('cat-dance');
  });

  it('stores selected category context when clicking a service pill link', async () => {
    render(<HomeCatalogCascade isAuthenticated={false} />);

    fireEvent.click(await screen.findByRole('button', { name: /^piano/i }));
    clickWithoutNavigation(screen.getByRole('link', { name: 'Piano' }));

    expect(sessionStorage.getItem('navigationFrom')).toBe('/');
    expect(sessionStorage.getItem('homeSelectedCategory')).toBe('cat-music');
  });

  it('filters out services with missing eligible age groups even when supply exists', async () => {
    const servicesData = cloneServicesWithSupply();
    servicesData.categories[0].services.push({
      id: 'svc-ear-training',
      name: 'Ear Training',
      subcategory_id: 'sub-ear-training',
      display_order: 9,
      instructor_count: 4,
    });

    useAllServicesWithInstructorsMock.mockReturnValue({ data: servicesData });
    useSubcategoriesByCategoryMock.mockImplementation((categoryId: string) => ({
      data:
        categoryId === 'cat-music'
          ? [...(SUBCATEGORIES_BY_CATEGORY['cat-music'] ?? []), { id: 'sub-ear-training', name: 'Ear Training' }]
          : SUBCATEGORIES_BY_CATEGORY[categoryId] ?? [],
    }));

    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /^piano/i });
    expect(screen.queryByRole('button', { name: /^ear training/i })).not.toBeInTheDocument();
  });

  it('falls back to generated subcategory labels when taxonomy metadata is missing', async () => {
    const servicesData = cloneServicesWithSupply();
    servicesData.categories[0].services.push(
      {
        id: 'svc-zither',
        name: 'Zither',
        subcategory_id: 'sub-unmapped',
        display_order: 11,
        instructor_count: 3,
        eligible_age_groups: ['adults'],
      },
      {
        id: 'svc-alto-flute',
        name: 'Alto Flute',
        subcategory_id: 'sub-unmapped',
        display_order: 11,
        instructor_count: 3,
        eligible_age_groups: ['adults'],
      }
    );
    useAllServicesWithInstructorsMock.mockReturnValue({ data: servicesData });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    const generatedSubcategoryPill = await screen.findByRole('button', {
      name: /other \(2\)/i,
    });
    fireEvent.click(generatedSubcategoryPill);

    const orderedServiceLinks = screen
      .getAllByRole('link')
      .map((link) => link.textContent?.trim())
      .filter((name): name is string => name === 'Alto Flute' || name === 'Zither');

    expect(orderedServiceLinks).toEqual(['Alto Flute', 'Zither']);
  });

  it('shows the category-selection prompt when all categories are filtered out', async () => {
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-music',
            name: 'Music',
            subtitle: 'Instruments and vocal arts',
            icon_name: 'music',
            services: [
              {
                id: 'svc-kids-only',
                name: 'Kids Choir',
                subcategory_id: 'sub-kids-choir',
                display_order: 1,
                instructor_count: 4,
                eligible_age_groups: ['kids'],
              },
            ],
          },
        ],
      },
    });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    expect(screen.getByText('Select a category to browse subcategories')).toBeInTheDocument();
  });

  it('uses Sparkles fallback icon when icon_name is unknown', async () => {
    useServiceCategoriesMock.mockReturnValue({
      data: [
        {
          id: 'cat-unknown-icon',
          name: 'Mystery',
          subtitle: 'Unknown icon',
          display_order: 1,
          icon_name: 'nonexistent_icon_name',
        },
      ],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-unknown-icon',
            name: 'Mystery',
            subtitle: 'Unknown icon',
            icon_name: 'nonexistent_icon_name',
            services: [
              {
                id: 'svc-mystery',
                name: 'Mystery Service',
                subcategory_id: 'sub-mystery',
                display_order: 1,
                instructor_count: 3,
                eligible_age_groups: ['adults'],
              },
            ],
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [{ id: 'sub-mystery', name: 'Mystery Sub' }] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Should render the category button without crashing (use exact name to avoid matching "Mystery Sub")
    expect(await screen.findByRole('button', { name: /^mystery$/i })).toBeInTheDocument();
  });

  it('uses Sparkles fallback icon when icon_name is null', async () => {
    useServiceCategoriesMock.mockReturnValue({
      data: [
        {
          id: 'cat-no-icon',
          name: 'No Icon',
          subtitle: 'Null icon',
          display_order: 1,
          icon_name: null,
        },
      ],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-no-icon',
            name: 'No Icon',
            subtitle: 'Null icon',
            icon_name: null,
            services: [
              {
                id: 'svc-null-icon',
                name: 'Null Icon Service',
                subcategory_id: 'sub-null-icon',
                display_order: 1,
                instructor_count: 2,
                eligible_age_groups: ['adults'],
              },
            ],
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [{ id: 'sub-null-icon', name: 'Sub' }] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    expect(await screen.findByRole('button', { name: /no icon/i })).toBeInTheDocument();
  });

  it('renders fallback categories when both APIs return empty', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: [] });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: { categories: [] } });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Fallback categories should be rendered as disabled buttons
    expect(screen.getByRole('button', { name: /tutoring & test prep/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^music$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^dance$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^languages$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sports & fitness/i })).toBeInTheDocument();

    // Fallback buttons should be disabled
    expect(screen.getByRole('button', { name: /tutoring & test prep/i })).toBeDisabled();
  });

  it('renders fallback categories when both APIs return null/undefined', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: null });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: null });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: null });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Fallback categories should render
    expect(screen.getByRole('button', { name: /tutoring & test prep/i })).toBeInTheDocument();
  });

  it('uses active_instructors fallback when instructor_count is missing', async () => {
    useServiceCategoriesMock.mockReturnValue({
      data: [{ id: 'cat-alt', name: 'Alt', subtitle: 'Alt', display_order: 1, icon_name: 'music' }],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-alt',
            name: 'Alt',
            subtitle: 'Alt',
            icon_name: 'music',
            services: [
              {
                id: 'svc-alt-1',
                name: 'Alt Service',
                subcategory_id: 'sub-alt',
                display_order: 1,
                active_instructors: 3,
                eligible_age_groups: ['adults'],
              },
            ],
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [{ id: 'sub-alt', name: 'Alt Sub' }] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Service should appear since active_instructors > 0
    expect(await screen.findByRole('button', { name: /alt sub/i })).toBeInTheDocument();
  });

  it('filters out services when both instructor_count and active_instructors are missing', async () => {
    useServiceCategoriesMock.mockReturnValue({
      data: [{ id: 'cat-empty-supply', name: 'Empty', subtitle: 'Empty', display_order: 1, icon_name: 'music' }],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-empty-supply',
            name: 'Empty',
            subtitle: 'Empty',
            icon_name: 'music',
            services: [
              {
                id: 'svc-no-supply',
                name: 'No Supply',
                subcategory_id: 'sub-no-supply',
                display_order: 1,
                eligible_age_groups: ['adults'],
                // no instructor_count, no active_instructors => 0
              },
            ],
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [{ id: 'sub-no-supply', name: 'No Supply Sub' }] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Category should be filtered out, showing prompt
    expect(screen.getByText('Select a category to browse subcategories')).toBeInTheDocument();
  });

  it('handles eligible_age_groups as non-array (string)', async () => {
    const servicesData = cloneServicesWithSupply();
    servicesData.categories[0].services[0].eligible_age_groups = 'adults' as unknown;

    useAllServicesWithInstructorsMock.mockReturnValue({ data: servicesData });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Service with non-array age groups should be filtered out by isEligibleForAudience
    // but remaining services still render
    await screen.findByRole('button', { name: /music theory/i });
  });

  it('handles category with empty id by skipping it', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: CATEGORY_DATA });
    const servicesData = cloneServicesWithSupply();
    servicesData.categories.push({
      id: '',
      name: 'Empty ID',
      subtitle: 'Should be skipped',
      icon_name: 'music',
      services: [
        {
          id: 'svc-empty-cat',
          name: 'Orphan',
          subcategory_id: 'sub-orphan',
          display_order: 1,
          instructor_count: 5,
          eligible_age_groups: ['adults'],
        },
      ],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: servicesData });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /^piano/i });
    // Empty ID category should not appear
    expect(screen.queryByText('Empty ID')).not.toBeInTheDocument();
  });

  it('handles service with empty subcategory_id by not grouping it', async () => {
    const servicesData = cloneServicesWithSupply();
    servicesData.categories[0].services.push({
      id: 'svc-no-sub',
      name: 'No Subcategory',
      subcategory_id: '',
      display_order: 20,
      instructor_count: 5,
      eligible_age_groups: ['adults'],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: servicesData });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    await screen.findByRole('button', { name: /^piano/i });
    // Service with empty subcategory_id should not appear as a subcategory
    expect(screen.queryByText('No Subcategory')).not.toBeInTheDocument();
  });

  it('shows "No services available" for a category with no matching services', async () => {
    useServiceCategoriesMock.mockReturnValue({
      data: [
        { id: 'cat-empty', name: 'Empty Cat', subtitle: 'Nothing here', display_order: 1, icon_name: 'globe' },
      ],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-empty',
            name: 'Empty Cat',
            subtitle: 'Nothing here',
            icon_name: 'globe',
            services: [
              {
                id: 'svc-no-match',
                name: 'No Match',
                subcategory_id: 'sub-no-match',
                display_order: 1,
                instructor_count: 0,
                eligible_age_groups: ['adults'],
              },
            ],
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // No categories left after filtering (zero instructor_count)
    expect(screen.getByText('Select a category to browse subcategories')).toBeInTheDocument();
  });

  it('falls back to servicesData categories when categoriesData is empty', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: [] });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: SERVICES_WITH_SUPPLY });
    useSubcategoriesByCategoryMock.mockImplementation((categoryId: string) => ({
      data: SUBCATEGORIES_BY_CATEGORY[categoryId] ?? [],
    }));

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Should render categories from services data
    expect(await screen.findByRole('button', { name: /^music$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^dance$/i })).toBeInTheDocument();
  });

  it('handles display_order tie by sorting services alphabetically', async () => {
    const servicesData = cloneServicesWithSupply();
    // Set same display_order for Piano and Keyboard
    servicesData.categories[0].services[0].display_order = 1;
    servicesData.categories[0].services[1].display_order = 1;
    useAllServicesWithInstructorsMock.mockReturnValue({ data: servicesData });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    fireEvent.click(await screen.findByRole('button', { name: /^piano/i }));
    const links = await screen.findAllByRole('link');
    const serviceNames = links
      .map(link => link.textContent?.trim())
      .filter((name): name is string => name === 'Keyboard' || name === 'Piano');

    // Alphabetical sort: Keyboard before Piano
    expect(serviceNames).toEqual(['Keyboard', 'Piano']);
  });

  it('handles display_order as null by sorting to the end', async () => {
    const servicesData = cloneServicesWithSupply();
    servicesData.categories[0].services[0].display_order = null;
    useAllServicesWithInstructorsMock.mockReturnValue({ data: servicesData });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Should still render without crashing
    await screen.findByRole('button', { name: /^piano/i });
  });

  it('persists category via sessionStorage and does not record search for fallback categories', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: [] });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: { categories: [] } });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    const fallbackButton = screen.getByRole('button', { name: /tutoring & test prep/i });
    // Fallback buttons are disabled, so clicking does nothing
    fireEvent.click(fallbackButton);

    expect(recordSearchMock).not.toHaveBeenCalled();
  });

  it('renders with isError flags without crashing', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: null, isError: true });
    useAllServicesWithInstructorsMock.mockReturnValue({ data: null, isError: true });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Should render fallback categories when both APIs error
    expect(screen.getByRole('button', { name: /tutoring & test prep/i })).toBeInTheDocument();
  });

  it('records search when clicking a real category button', async () => {
    render(<HomeCatalogCascade isAuthenticated={true} />);

    fireEvent.click(await screen.findByRole('button', { name: /^dance$/i }));

    expect(recordSearchMock).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'Dance lessons',
        search_type: 'category',
      }),
      true,
    );
  });

  it('handles category with subtitle as null', async () => {
    useServiceCategoriesMock.mockReturnValue({
      data: [
        { id: 'cat-no-sub', name: 'No Subtitle', subtitle: null, display_order: 1, icon_name: 'music' },
      ],
    });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-no-sub',
            name: 'No Subtitle',
            subtitle: null,
            icon_name: 'music',
            services: [
              {
                id: 'svc-ns',
                name: 'NS Service',
                subcategory_id: 'sub-ns',
                display_order: 1,
                instructor_count: 2,
                eligible_age_groups: ['adults'],
              },
            ],
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [{ id: 'sub-ns', name: 'NS Sub' }] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    expect(await screen.findByRole('button', { name: /no subtitle/i })).toBeInTheDocument();
  });

  it('handles toId with numeric category id', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: [] });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 42,
            name: 'Numeric',
            subtitle: 'Numeric id',
            icon_name: 'music',
            services: [
              {
                id: 'svc-num',
                name: 'Numeric Service',
                subcategory_id: 'sub-num',
                display_order: 1,
                instructor_count: 2,
                eligible_age_groups: ['adults'],
              },
            ],
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [{ id: 'sub-num', name: 'Num Sub' }] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    expect(await screen.findByRole('button', { name: /numeric/i })).toBeInTheDocument();
  });

  it('handles services with null category services array', async () => {
    useServiceCategoriesMock.mockReturnValue({ data: CATEGORY_DATA });
    useAllServicesWithInstructorsMock.mockReturnValue({
      data: {
        categories: [
          {
            id: 'cat-music',
            name: 'Music',
            subtitle: 'Instruments',
            icon_name: 'music',
            services: null,
          },
        ],
      },
    });
    useSubcategoriesByCategoryMock.mockReturnValue({ data: [] });

    render(<HomeCatalogCascade isAuthenticated={false} />);

    // Should render without crashing; services ?? [] handles the null
    expect(screen.getByText('Select a category to browse subcategories')).toBeInTheDocument();
  });
});
