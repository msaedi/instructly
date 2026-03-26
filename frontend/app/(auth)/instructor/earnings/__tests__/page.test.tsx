import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import InstructorEarningsPage from '../page';
import { useCommissionStatus } from '@/hooks/queries/useCommissionStatus';
import { useInstructorEarnings } from '@/hooks/queries/useInstructorEarnings';
import { useInstructorPayouts } from '@/hooks/queries/useInstructorPayouts';
import { fetchWithAuth } from '@/lib/api';
import { toast } from 'sonner';

jest.mock('@/components/UserProfileDropdown', () => {
  const MockUserProfileDropdown = () => <div data-testid="user-dropdown" />;
  MockUserProfileDropdown.displayName = 'MockUserProfileDropdown';
  return {
    __esModule: true,
    default: MockUserProfileDropdown,
  };
});
jest.mock('../../_embedded/EmbeddedContext', () => ({
  useEmbedded: () => false,
}));
jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));
jest.mock('@/hooks/queries/useCommissionStatus');
jest.mock('@/hooks/queries/useInstructorEarnings');
jest.mock('@/hooks/queries/useInstructorPayouts');

const mockUseCommissionStatus = useCommissionStatus as jest.MockedFunction<typeof useCommissionStatus>;
const mockUseInstructorEarnings = useInstructorEarnings as jest.MockedFunction<typeof useInstructorEarnings>;
const mockUseInstructorPayouts = useInstructorPayouts as jest.MockedFunction<typeof useInstructorPayouts>;
const mockFetchWithAuth = fetchWithAuth as jest.MockedFunction<typeof fetchWithAuth>;
const mockToastSuccess = toast.success as jest.MockedFunction<typeof toast.success>;
const mockToastError = toast.error as jest.MockedFunction<typeof toast.error>;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  const renderResult = render(
    <QueryClientProvider client={queryClient}>
      <InstructorEarningsPage />
    </QueryClientProvider>
  );

  return { queryClient, ...renderResult };
}

describe('Instructor earnings page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseCommissionStatus.mockReturnValue({
      data: {
        is_founding: false,
        tier_name: 'entry',
        commission_rate_pct: 15,
        activity_window_days: 30,
        completed_lessons_30d: 3,
        next_tier_name: 'growth',
        next_tier_threshold: 5,
        lessons_to_next_tier: 2,
        tiers: [
          {
            name: 'entry',
            display_name: 'Entry',
            commission_pct: 15,
            min_lessons: 1,
            max_lessons: 4,
            is_current: true,
            is_unlocked: true,
          },
          {
            name: 'growth',
            display_name: 'Growth',
            commission_pct: 12,
            min_lessons: 5,
            max_lessons: 10,
            is_current: false,
            is_unlocked: false,
          },
          {
            name: 'pro',
            display_name: 'Pro',
            commission_pct: 10,
            min_lessons: 11,
            max_lessons: null,
            is_current: false,
            is_unlocked: false,
          },
        ],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCommissionStatus>);

    mockUseInstructorEarnings.mockReturnValue({
      data: {
        total_lesson_value: 80000,
        total_earned: 68000,
        total_fees: 12540,
        booking_count: 7,
        service_count: 7,
        hours_invoiced: 4,
        invoices: [
          {
            booking_id: 'bk_1',
            lesson_date: '2026-01-01',
            start_time: '10:00:00',
            service_name: 'Piano Basics',
            student_name: 'Emma J.',
            duration_minutes: 60,
            total_paid_cents: 12000,
            tip_cents: 2000,
            instructor_share_cents: 9000,
            lesson_price_cents: 12000,
            platform_fee_cents: 1000,
            platform_fee_rate: 0.1,
            student_fee_cents: 1200,
            status: 'paid',
            created_at: '2026-01-01T15:00:00Z',
          },
        ],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useInstructorEarnings>);

    mockUseInstructorPayouts.mockReturnValue({
      data: {
        payouts: [
          {
            id: 'po_1',
            amount_cents: 68000,
            created_at: '2027-02-12T14:00:00Z',
            arrival_date: '2027-02-18',
            status: 'paid',
            failure_code: null,
            failure_message: null,
          },
        ],
        total_paid_cents: 0,
        total_pending_cents: 0,
        payout_count: 1,
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useInstructorPayouts>);

    mockFetchWithAuth.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['csv-content'], { type: 'text/csv' }),
      headers: new Headers({
        'content-type': 'text/csv',
        'content-disposition': 'attachment; filename="earnings.csv"',
      }),
    } as unknown as Response);

    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: jest.fn(() => 'blob:earnings'),
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: jest.fn(),
    });
    Object.defineProperty(HTMLAnchorElement.prototype, 'click', {
      configurable: true,
      writable: true,
      value: jest.fn(),
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('renders three earnings stat cards and invoice rows with totals', () => {
    const { container } = renderPage();
    const grossHeading = screen.getByText('Gross Earnings');
    const commissionSummary = screen.getByText('Entry tier · 15%');

    expect(container.querySelectorAll('.insta-dashboard-stat-card')).toHaveLength(3);
    expect(grossHeading.compareDocumentPosition(commissionSummary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText('Gross Earnings')).toBeInTheDocument();
    expect(screen.getByText('Net Earnings')).toBeInTheDocument();
    expect(screen.getByText('Lessons')).toBeInTheDocument();
    expect(screen.getByText('$800.00')).toBeInTheDocument();
    expect(screen.getByText('$680.00')).toBeInTheDocument();
    expect(screen.getByText('4 hrs')).toBeInTheDocument();
    expect(screen.getByText('Entry tier · 15%')).toBeInTheDocument();
    expect(screen.getByText('3 lessons completed · in the last 30 days')).toBeInTheDocument();
    expect(screen.getByTestId('commission-tier-track-entry')).toHaveAttribute(
      'data-filled-dots',
      '3'
    );
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByText('Piano Basics')).toBeInTheDocument();
    expect(screen.getByText('Emma J.')).toBeInTheDocument();
    expect(screen.getByText('$120.00')).toBeInTheDocument();
    expect(screen.getByText('$10.00')).toBeInTheDocument(); // platform fee
    expect(screen.getByText('$90.00')).toBeInTheDocument(); // instructor share
    expect(screen.getByText('$20.00')).toBeInTheDocument(); // tip
  });

  it('shows dynamic export years and defaults the modal to the current year', async () => {
    const user = userEvent.setup();

    renderPage();

    await user.click(screen.getByRole('button', { name: 'Export transactions' }));

    const yearField = screen.getByText('Year').parentElement;
    expect(yearField).not.toBeNull();
    const yearButton = within(yearField as HTMLElement).getByRole('button');
    expect(yearButton).toHaveTextContent(String(new Date().getFullYear()));

    await user.click(yearButton);

    expect(screen.queryByRole('option', { name: '2025' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2026' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '2027' })).toBeInTheDocument();
  });

  it('shows the refreshed empty invoice copy', () => {
    mockUseInstructorEarnings.mockReturnValue({
      data: {
        total_lesson_value: 0,
        total_earned: 0,
        total_fees: 0,
        booking_count: 0,
        service_count: 0,
        hours_invoiced: 0,
        invoices: [],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useInstructorEarnings>);

    renderPage();

    expect(
      screen.getByText('No invoices yet — completed lessons will appear here.')
    ).toBeInTheDocument();
  });

  it('shows the refreshed empty payouts copy', async () => {
    const user = userEvent.setup();
    mockUseInstructorPayouts.mockReturnValue({
      data: {
        payouts: [],
        total_paid_cents: 0,
        total_pending_cents: 0,
        payout_count: 0,
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useInstructorPayouts>);

    renderPage();

    await user.click(screen.getByRole('tab', { name: /payouts/i }));

    expect(
      screen.getByText('No payouts yet — earnings are sent to your bank automatically.')
    ).toBeInTheDocument();
  });

  it('shows a success toast after exporting a report', async () => {
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const invalidateSpy = jest
      .spyOn(queryClient, 'invalidateQueries')
      .mockResolvedValue(undefined);

    await user.click(screen.getByRole('button', { name: 'Export transactions' }));

    const fileTypeField = screen.getByText('File Type').parentElement;
    expect(fileTypeField).not.toBeNull();
    const fileTypeButton = within(fileTypeField as HTMLElement).getByRole('button');
    await user.click(fileTypeButton);
    await user.click(screen.getByRole('option', { name: 'CSV' }));
    await user.click(screen.getByRole('button', { name: 'Download Report' }));

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith('Export downloaded');
    });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['instructor', 'earnings'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['instructor', 'payouts'] });
  });

  it('shows an error toast when export fails', async () => {
    const user = userEvent.setup();
    mockFetchWithAuth.mockResolvedValueOnce({
      ok: false,
      blob: async () => new Blob(),
      headers: new Headers(),
    } as unknown as Response);

    renderPage();

    await user.click(screen.getByRole('button', { name: 'Export transactions' }));

    const fileTypeField = screen.getByText('File Type').parentElement;
    expect(fileTypeField).not.toBeNull();
    const fileTypeButton = within(fileTypeField as HTMLElement).getByRole('button');
    await user.click(fileTypeButton);
    await user.click(screen.getByRole('option', { name: 'CSV' }));
    await user.click(screen.getByRole('button', { name: 'Download Report' }));

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Export failed. Please try again.');
    });
  });
});
