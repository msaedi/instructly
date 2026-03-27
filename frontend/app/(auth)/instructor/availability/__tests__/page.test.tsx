import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InstructorAvailabilityPage from '../page';
import { queryKeys } from '@/src/api/queryKeys';

const mockSaveWeek = jest.fn();
const mockApplyToFutureWeeks = jest.fn();
const mockRefreshSchedule = jest.fn();
const mockFetchBookedSlots = jest.fn();
const mockInvalidateWeekSnapshot = jest.fn();
const mockUpdateCalendarSettings = jest.fn();
const mockAcknowledgeCalendarSettings = jest.fn();
const mockWeekView = jest.fn();

const baseWeekBits = {
  '2026-03-16': new Uint8Array([1]),
};

const savedWeekBits = {
  '2026-03-16': new Uint8Array([0]),
};

const baseWeekTags = {
  '2026-03-16': new Uint8Array(72),
};

const savedWeekTags = {
  '2026-03-16': new Uint8Array(72),
};

jest.mock('sonner', () => ({
  toast: Object.assign(jest.fn(), {
    error: jest.fn(),
    success: jest.fn(),
    warning: jest.fn(),
    info: jest.fn(),
  }),
}));

const mockedToast = jest.requireMock('sonner').toast as jest.Mock & {
  error: jest.Mock;
  success: jest.Mock;
  warning: jest.Mock;
  info: jest.Mock;
};

jest.mock('next/dynamic', () => (loadFn: () => Promise<unknown>) => {
  try {
    Promise.resolve(loadFn()).catch(() => {});
  } catch {}

  const MockDynamic = (props: Record<string, unknown>) => {
    if ('weekDates' in props) {
      mockWeekView(props);
      return <div data-testid="mock-week-view" />;
    }
    if ('open' in props && 'onOverwrite' in props) {
      return props['open'] ? <div data-testid="mock-conflict-modal" role="dialog" /> : null;
    }
    return <div data-testid="mock-dynamic-component" />;
  };

  MockDynamic.displayName = 'MockDynamic';
  return MockDynamic;
});

jest.mock('@/components/availability/WeekNavigator', () => ({
  __esModule: true,
  default: () => <div data-testid="week-header" />,
}));

jest.mock('@/components/dashboard/SectionHeroCard', () => ({
  SectionHeroCard: ({ title }: { title: string }) => <div>{title}</div>,
}));

jest.mock('@/hooks/availability/useAvailability', () => ({
  useAvailability: jest.fn(() => ({
    currentWeekStart: new Date('2026-03-16T00:00:00.000Z'),
    weekBits: baseWeekBits,
    savedWeekBits,
    weekTags: baseWeekTags,
    savedWeekTags,
    hasUnsavedChanges: true,
    isLoading: false,
    navigateWeek: jest.fn(),
    setWeekBits: jest.fn(),
    setWeekTags: jest.fn(),
    setMessage: jest.fn(),
    message: null,
    refreshSchedule: mockRefreshSchedule,
    version: 'v1',
    lastModified: '2026-03-13T12:00:00.000Z',
    saveWeek: mockSaveWeek,
    applyToFutureWeeks: mockApplyToFutureWeeks,
    goToCurrentWeek: jest.fn(),
    allowPastEdits: true,
  })),
}));

jest.mock('@/hooks/availability/useBookedSlots', () => ({
  useBookedSlots: jest.fn(() => ({
    bookedSlots: [],
    fetchBookedSlots: mockFetchBookedSlots,
  })),
}));

jest.mock('@/hooks/queries/useAuth', () => ({
  useAuth: jest.fn(() => ({
    user: {
      id: 'instructor-user',
      timezone: 'America/New_York',
    },
  })),
}));

jest.mock('@/hooks/queries/useInstructorProfileMe', () => {
  const React = require('react');
  const { useQueryClient } = require('@tanstack/react-query');
  const { queryKeys } = require('@/src/api/queryKeys');

  return {
    useInstructorProfileMe: jest.fn(() => {
      const queryClient = useQueryClient();
      const data = React.useSyncExternalStore(
        (onStoreChange: () => void) => queryClient.getQueryCache().subscribe(onStoreChange),
        () => queryClient.getQueryData(queryKeys.instructors.me),
        () => queryClient.getQueryData(queryKeys.instructors.me)
      );
      return {
        data,
        isLoading: false,
      };
    }),
  };
});

jest.mock('@/features/instructor-profile/hooks/useAvailabilityWeekInvalidation', () => ({
  useAvailabilityWeekInvalidation: jest.fn(() => mockInvalidateWeekSnapshot),
}));

jest.mock('../../_embedded/EmbeddedContext', () => ({
  useEmbedded: jest.fn(() => false),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/src/api/generated/instructors-v1/instructors-v1', () => ({
  useUpdateCalendarSettingsApiV1InstructorsMeCalendarSettingsPatch: jest.fn(() => ({
    mutateAsync: mockUpdateCalendarSettings,
    isPending: false,
  })),
  useAcknowledgeCalendarSettingsApiV1InstructorsMeCalendarSettingsAcknowledgePost: jest.fn(() => ({
    mutateAsync: mockAcknowledgeCalendarSettings,
    isPending: false,
  })),
}));

type RenderOptions = {
  acknowledgedAt?: string | null;
  formatPrices?: Array<{ format: 'student_location' | 'instructor_location' | 'online'; hourly_rate: number }>;
};

function buildInstructorProfile({
  acknowledgedAt = null,
  formatPrices = [{ format: 'online' as const, hourly_rate: 75 }],
}: RenderOptions = {}) {
  return {
    id: 'instructor-profile',
    user_id: 'user-1',
    bio: 'Bio',
    years_experience: 4,
    favorited_count: 0,
    services: [
      {
        id: 'service-1',
        service_catalog_id: 'catalog-1',
        service_catalog_name: 'Piano',
        min_hourly_rate: 75,
        format_prices: formatPrices,
        description: null,
      },
    ],
    user: {
      first_name: 'Taylor',
      last_initial: 'Q.',
    },
    non_travel_buffer_minutes: 15,
    travel_buffer_minutes: 60,
    overnight_protection_enabled: true,
    calendar_settings_acknowledged_at: acknowledgedAt,
  };
}

function renderPage(options: RenderOptions = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  queryClient.setQueryData(queryKeys.instructors.me, buildInstructorProfile(options));

  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <InstructorAvailabilityPage />
    </QueryClientProvider>
  );

  return {
    ...view,
    queryClient,
    user,
  };
}

describe('InstructorAvailabilityPage', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: jest.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
    });
    Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', {
      configurable: true,
      value: jest.fn(() => false),
    });
    Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
      configurable: true,
      value: jest.fn(),
    });
    Object.defineProperty(HTMLElement.prototype, 'releasePointerCapture', {
      configurable: true,
      value: jest.fn(),
    });
  });

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mockSaveWeek.mockResolvedValue({
      success: true,
      message: 'Availability saved',
    });
    mockApplyToFutureWeeks.mockResolvedValue({
      success: true,
      message: 'Applied schedule to future range',
    });
    mockRefreshSchedule.mockResolvedValue(undefined);
    mockFetchBookedSlots.mockResolvedValue(undefined);
    mockInvalidateWeekSnapshot.mockResolvedValue(undefined);
    mockUpdateCalendarSettings.mockImplementation(async ({ data }: { data: Record<string, unknown> }) => data);
    mockAcknowledgeCalendarSettings.mockResolvedValue({
      calendar_settings_acknowledged_at: '2026-03-13T23:00:00Z',
    });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders the settings section with instructor defaults from profile', () => {
    renderPage();

    expect(
      screen.getByRole('heading', { name: 'Buffer between back-to-back lessons' })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: 'Staying put buffer' })
    ).toHaveTextContent('15 min');
    expect(
      screen.getByRole('combobox', { name: 'Traveling to student buffer' })
    ).toHaveTextContent('60 min');
    expect(
      screen.getByRole('switch', { name: 'Overnight booking protection' })
    ).toHaveAttribute('aria-checked', 'true');
  });

  it('shows the paint toolbar for mixed-format instructors and passes tag props to the week view', async () => {
    const { user } = renderPage({
      formatPrices: [
        { format: 'student_location', hourly_rate: 95 },
        { format: 'online', hourly_rate: 80 },
      ],
    });

    expect(screen.getByTestId('availability-paint-toolbar')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /All/i })).toBeInTheDocument();
    expect(screen.getAllByRole('radio').map((item) => item.textContent)).toEqual([
      expect.stringContaining('All'),
      expect.stringContaining('Online'),
    ]);
    expect(mockWeekView).toHaveBeenCalledWith(
      expect.objectContaining({
        weekTags: baseWeekTags,
        availableTagOptions: [1],
        paintMode: 0,
      })
    );

    await user.click(screen.getByRole('radio', { name: /Online/i }));

    await waitFor(() =>
      expect(mockWeekView).toHaveBeenLastCalledWith(
        expect.objectContaining({
          paintMode: 1,
        })
      )
    );
  });

  it('keeps the controls and toolbar above the grid', () => {
    renderPage({
      formatPrices: [
        { format: 'student_location', hourly_rate: 95 },
        { format: 'instructor_location', hourly_rate: 85 },
        { format: 'online', hourly_rate: 80 },
      ],
    });

    const teachingWindow = screen.getByText('Teaching window');
    const toolbar = screen.getByTestId('availability-paint-toolbar');
    const grid = screen.getByTestId('mock-week-view');

    // Controls row → toolbar → grid (all above the calendar)
    expect(
      teachingWindow.compareDocumentPosition(toolbar) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      toolbar.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('hides the paint toolbar for single-format instructors', () => {
    renderPage({
      formatPrices: [
        { format: 'online', hourly_rate: 75 },
      ],
    });

    expect(screen.queryByTestId('availability-paint-toolbar')).not.toBeInTheDocument();
  });

  it('auto-saves the full settings payload after debounced edits and collapses rapid changes', async () => {
    const { user } = renderPage();

    await user.click(screen.getByRole('combobox', { name: 'Staying put buffer' }));
    await user.click(screen.getByRole('option', { name: '30 min' }));
    await user.click(screen.getByRole('combobox', { name: 'Traveling to student buffer' }));
    await user.click(screen.getByRole('option', { name: '90 min' }));
    await user.click(screen.getByRole('switch', { name: 'Overnight booking protection' }));

    expect(mockUpdateCalendarSettings).not.toHaveBeenCalled();

    await act(async () => {
      jest.advanceTimersByTime(1200);
    });

    await waitFor(() =>
      expect(mockUpdateCalendarSettings).toHaveBeenCalledWith({
        data: {
          non_travel_buffer_minutes: 30,
          travel_buffer_minutes: 90,
          overnight_protection_enabled: false,
        },
      })
    );

    expect(mockUpdateCalendarSettings).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('calendar-settings-save-state')).toHaveTextContent('Saved');
  });

  it('does not show the acknowledgement popup for settings autosave alone', async () => {
    const { user } = renderPage();

    await user.click(screen.getByRole('switch', { name: 'Overnight booking protection' }));

    await act(async () => {
      jest.advanceTimersByTime(1200);
    });

    await waitFor(() => expect(mockUpdateCalendarSettings).toHaveBeenCalledTimes(1));

    expect(
      screen.queryByTestId('calendar-settings-acknowledgement-modal')
    ).not.toBeInTheDocument();
  });

  it('shows the first-save popup after a successful grid save and records acknowledgement', async () => {
    const { user } = renderPage({
      acknowledgedAt: null,
      formatPrices: [
        { format: 'student_location', hourly_rate: 95 },
        { format: 'online', hourly_rate: 80 },
      ],
    });

    await user.click(screen.getByRole('button', { name: 'Save Week' }));

    await waitFor(() =>
      expect(screen.getByTestId('calendar-settings-acknowledgement-modal')).toBeInTheDocument()
    );
    expect(
      screen.getByText(/15 minutes between lessons when you're staying put/i)
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'OK' }));

    await waitFor(() => expect(mockAcknowledgeCalendarSettings).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(
        screen.queryByTestId('calendar-settings-acknowledgement-modal')
      ).not.toBeInTheDocument()
    );

    await user.click(screen.getByRole('button', { name: 'Save Week' }));

    await waitFor(() => expect(mockSaveWeek).toHaveBeenCalledTimes(2));
    expect(
      screen.queryByTestId('calendar-settings-acknowledgement-modal')
    ).not.toBeInTheDocument();
  });

  it('does not show the popup when calendar settings were already acknowledged', async () => {
    const { user } = renderPage({
      acknowledgedAt: '2026-03-12T20:00:00Z',
    });

    await user.click(screen.getByRole('button', { name: 'Save Week' }));

    await waitFor(() => expect(mockSaveWeek).toHaveBeenCalledTimes(1));
    expect(
      screen.queryByTestId('calendar-settings-acknowledgement-modal')
    ).not.toBeInTheDocument();
  });

  it('shows an error toast when calendar settings autosave fails', async () => {
    mockUpdateCalendarSettings.mockRejectedValueOnce(new Error('nope'));
    const { user } = renderPage();

    await user.click(screen.getByRole('switch', { name: 'Overnight booking protection' }));

    await act(async () => {
      jest.advanceTimersByTime(1200);
    });

    await waitFor(() =>
      expect(mockedToast.error).toHaveBeenCalledWith('Failed to save calendar settings')
    );
    expect(
      screen.queryByTestId('calendar-settings-acknowledgement-modal')
    ).not.toBeInTheDocument();
  });

  it('opens the protections modal from the about link', async () => {
    const { user } = renderPage({
      acknowledgedAt: '2026-03-12T20:00:00Z',
    });

    await user.click(screen.getByRole('button', { name: 'About calendar protections' }));

    expect(screen.getByTestId('calendar-settings-acknowledgement-modal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
    expect(mockAcknowledgeCalendarSettings).not.toHaveBeenCalled();
  });
});
