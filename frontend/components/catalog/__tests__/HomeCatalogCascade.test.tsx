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
      name: /subcategory 3 \(2\)/i,
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
});
