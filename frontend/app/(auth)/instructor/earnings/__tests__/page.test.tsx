import { render, screen } from '@testing-library/react';

import InstructorEarningsPage from '../page';
import { useInstructorEarnings } from '@/hooks/queries/useInstructorEarnings';
import { useInstructorPayouts } from '@/hooks/queries/useInstructorPayouts';

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
jest.mock('@/hooks/queries/useInstructorEarnings');
jest.mock('@/hooks/queries/useInstructorPayouts');

const mockUseInstructorEarnings = useInstructorEarnings as jest.MockedFunction<typeof useInstructorEarnings>;
const mockUseInstructorPayouts = useInstructorPayouts as jest.MockedFunction<typeof useInstructorPayouts>;

describe('Instructor earnings page', () => {
  beforeEach(() => {
    mockUseInstructorEarnings.mockReturnValue({
      data: {
        total_earned: 68000,
        total_fees: 12540,
        booking_count: 7,
        service_count: 7,
        hours_invoiced: 4,
        invoices: [
          {
            booking_id: 'bk_1',
            lesson_date: '2025-01-01',
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
            created_at: '2025-01-01T15:00:00Z',
          },
        ],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useInstructorEarnings>);

    mockUseInstructorPayouts.mockReturnValue({
      data: {
        payouts: [],
        total_paid_cents: 0,
        total_pending_cents: 0,
        payout_count: 0,
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useInstructorPayouts>);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('renders invoice rows with totals', () => {
    render(<InstructorEarningsPage />);
    expect(screen.getByText('Piano Basics')).toBeInTheDocument();
    expect(screen.getByText('Emma J.')).toBeInTheDocument();
    expect(screen.getByText('$120.00')).toBeInTheDocument();
    expect(screen.getByText('$10.00')).toBeInTheDocument(); // platform fee
    expect(screen.getByText('$90.00')).toBeInTheDocument(); // instructor share
    expect(screen.getByText('$20.00')).toBeInTheDocument(); // tip
  });
});
