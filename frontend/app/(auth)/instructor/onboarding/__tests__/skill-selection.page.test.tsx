import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Step3SkillsPricing from '@/app/(auth)/instructor/onboarding/skill-selection/page';
import { useOnboardingStepStatus } from '@/features/instructor-onboarding/useOnboardingStepStatus';
import { useServiceCategories, useAllServicesWithInstructors } from '@/hooks/queries/useServices';
import { useCategoriesWithSubcategories, useSubcategoryFilters } from '@/hooks/queries/useTaxonomy';

const searchParamsProxy = {
  get: (_key: string) => null,
  toString: () => '',
};

jest.mock('next/navigation', () => ({
  useSearchParams: () => searchParamsProxy,
}));

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'user-1', roles: ['instructor'] },
    isAuthenticated: true,
  }),
}));

jest.mock('@/features/instructor-onboarding/OnboardingProgressHeader', () => ({
  OnboardingProgressHeader: () => <div data-testid="onboarding-progress-header" />,
}));

jest.mock('@/features/instructor-onboarding/useOnboardingStepStatus', () => ({
  useOnboardingStepStatus: jest.fn(),
}));

jest.mock('@/lib/pricing/usePricingFloors', () => ({
  usePricingConfig: () => ({ config: null }),
}));

jest.mock('@/hooks/usePlatformConfig', () => ({
  usePlatformFees: () => ({
    fees: {
      tier_1: 0.3,
      founding_instructor: 0.15,
    },
  }),
}));

jest.mock('@/hooks/queries/useServices', () => ({
  useServiceCategories: jest.fn(),
  useAllServicesWithInstructors: jest.fn(),
}));

jest.mock('@/hooks/queries/useTaxonomy', () => ({
  useCategoriesWithSubcategories: jest.fn(),
  useSubcategoryFilters: jest.fn(),
}));

jest.mock('@/components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({
    checked,
    onChange,
    ariaLabel,
    disabled,
  }: {
    checked: boolean;
    onChange: () => void;
    ariaLabel: string;
    disabled?: boolean;
  }) => (
    <button
      type="button"
      aria-label={ariaLabel}
      aria-pressed={checked}
      disabled={disabled}
      onClick={onChange}
    />
  ),
}));

const useOnboardingStepStatusMock = useOnboardingStepStatus as jest.Mock;
const useServiceCategoriesMock = useServiceCategories as jest.Mock;
const useAllServicesWithInstructorsMock = useAllServicesWithInstructors as jest.Mock;
const useCategoriesWithSubcategoriesMock = useCategoriesWithSubcategories as jest.Mock;
const useSubcategoryFiltersMock = useSubcategoryFilters as jest.Mock;

const CATEGORY_DATA = [
  {
    id: 'cat-1',
    name: 'Music',
    display_order: 1,
    description: null,
    icon_name: null,
    subtitle: null,
  },
];

const SERVICES_RESPONSE = {
  categories: [
    {
      id: 'cat-1',
      name: 'Music',
      description: null,
      icon_name: null,
      subtitle: null,
      services: [
        {
          id: 'svc-1',
          name: 'Piano',
          subcategory_id: 'sub-1',
          eligible_age_groups: ['kids', 'teens', 'adults'],
          active_instructors: 2,
          demand_score: 10,
          instructor_count: 2,
          is_trending: false,
          display_order: 1,
        },
      ],
    },
  ],
  metadata: {
    cached_for_seconds: 60,
    total_categories: 1,
    total_services: 1,
    updated_at: '2026-02-08T00:00:00Z',
  },
};

const CATEGORIES_WITH_SUBCATEGORIES = [
  {
    id: 'cat-1',
    name: 'Music',
    display_order: 1,
    description: null,
    icon_name: null,
    subtitle: null,
    subcategories: [
      {
        id: 'sub-1',
        name: 'Piano',
        service_count: 1,
      },
    ],
  },
];

const SUBCATEGORY_FILTERS = [
  {
    filter_key: 'skill_level',
    filter_display_name: 'Skill Level',
    filter_type: 'multi_select',
    options: [
      { id: 'sl-1', value: 'beginner', display_name: 'Beginner', display_order: 0 },
      {
        id: 'sl-2',
        value: 'intermediate',
        display_name: 'Intermediate',
        display_order: 1,
      },
      { id: 'sl-3', value: 'advanced', display_name: 'Advanced', display_order: 2 },
    ],
  },
  {
    filter_key: 'goal',
    filter_display_name: 'Goal',
    filter_type: 'multi_select',
    options: [
      { id: 'goal-1', value: 'hobby', display_name: 'Hobby', display_order: 0 },
      {
        id: 'goal-2',
        value: 'performance',
        display_name: 'Performance',
        display_order: 1,
      },
    ],
  },
];

const renderWithClient = (ui: ReactNode) => {
  const queryClient = new QueryClient();
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
};

describe('Skill selection page refine header', () => {
  beforeEach(() => {
    useOnboardingStepStatusMock.mockReturnValue({
      stepStatus: {
        'account-setup': 'done',
        'skill-selection': 'pending',
        'verify-identity': 'pending',
        'payment-setup': 'pending',
      },
      rawData: {
        profile: {
          is_live: false,
          is_founding_instructor: false,
          services: [],
          service_area_neighborhoods: [],
          service_area_boroughs: [],
          service_area_summary: '',
          preferred_teaching_locations: [],
          current_tier_pct: null,
        },
      },
    });

    useServiceCategoriesMock.mockReturnValue({
      data: CATEGORY_DATA,
      isLoading: false,
      error: null,
    });

    useAllServicesWithInstructorsMock.mockReturnValue({
      data: SERVICES_RESPONSE,
      isLoading: false,
      error: null,
    });

    useCategoriesWithSubcategoriesMock.mockReturnValue({
      data: CATEGORIES_WITH_SUBCATEGORIES,
      isLoading: false,
      error: null,
    });

    useSubcategoryFiltersMock.mockImplementation((subcategoryId: string) => ({
      data: subcategoryId === 'sub-1' ? SUBCATEGORY_FILTERS : [],
      isLoading: false,
      error: null,
    }));
  });

  it('renders refine label as selectable text and toggles via chevron button only', async () => {
    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByRole('button', { name: /music/i }));
    fireEvent.click(await screen.findByRole('button', { name: /toggle subcategory piano/i }));
    fireEvent.click(await screen.findByRole('button', { name: /add service piano/i }));

    const refineLabel = await screen.findByText('Refine what you teach (optional)');
    expect(refineLabel).toBeInTheDocument();
    expect(refineLabel).toHaveClass('text-gray-900');
    expect(refineLabel).toHaveClass('select-text');

    expect(
      screen.queryByRole('button', { name: /refine what you teach \(optional\)/i })
    ).not.toBeInTheDocument();

    const toggleButton = screen.getByRole('button', {
      name: /toggle refine filters for piano/i,
    });
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Goal')).not.toBeInTheDocument();

    fireEvent.click(toggleButton);

    await waitFor(() => {
      expect(toggleButton).toHaveAttribute('aria-expanded', 'true');
    });
    expect(screen.getByText('Goal')).toBeInTheDocument();

    expect(screen.getByText('Age Groups')).toBeInTheDocument();
    expect(screen.getByText('Skill Level')).toBeInTheDocument();
  });

  it('supports expanding and collapsing subcategories inside an expanded category', async () => {
    renderWithClient(<Step3SkillsPricing />);

    fireEvent.click(screen.getByRole('button', { name: /music/i }));

    const subcategoryToggle = screen.getByRole('button', {
      name: /toggle subcategory piano/i,
    });

    expect(subcategoryToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /add service piano/i })).not.toBeInTheDocument();

    fireEvent.click(subcategoryToggle);
    expect(subcategoryToggle).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByRole('button', { name: /add service piano/i })).toBeInTheDocument();

    fireEvent.click(subcategoryToggle);
    expect(subcategoryToggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /add service piano/i })).not.toBeInTheDocument();
  });
});
