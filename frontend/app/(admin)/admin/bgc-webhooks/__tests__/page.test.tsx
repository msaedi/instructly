import type { ReactElement } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AdminBGCWebhookPage from '../page';
import type { WebhookLogItem } from '../hooks';
import { useBGCWebhookLogs, useBGCWebhookStats } from '../hooks';

jest.mock('../hooks', () => {
  const actual = jest.requireActual('../hooks');
  return {
    ...actual,
    useBGCWebhookLogs: jest.fn(),
    useBGCWebhookStats: jest.fn(),
  };
});

jest.mock('@/hooks/useAdminAuth', () => ({
  useAdminAuth: () => ({ isAdmin: true, isLoading: false }),
}));

const mockLogout = jest.fn();

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ logout: mockLogout }),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

const mockedUseWebhookLogs = useBGCWebhookLogs as jest.MockedFunction<typeof useBGCWebhookLogs>;
const mockedUseWebhookStats = useBGCWebhookStats as jest.MockedFunction<typeof useBGCWebhookStats>;

const sampleLogs: WebhookLogItem[] = [
  {
    id: 'log_1',
    event_type: 'report.completed',
    delivery_id: 'delivery-1',
    http_status: 200,
    signature: 'sig123',
    created_at: new Date().toISOString(),
    payload: { type: 'report.completed' },
    instructor_id: '01TESTABC',
    report_id: 'rpt_123',
    candidate_id: 'cand_1',
    invitation_id: 'inv_1',
  },
];

beforeEach(() => {
  mockedUseWebhookLogs.mockReturnValue({
    logs: sampleLogs,
    errorCount24h: 1,
    fetchNextPage: jest.fn(),
    hasNextPage: false,
    isPending: false,
    isFetching: false,
    isFetchingNextPage: false,
    refetch: jest.fn(),
  });
  mockedUseWebhookStats.mockReturnValue({
    data: { error_count_24h: 1 },
    refetch: jest.fn(),
  } as unknown as ReturnType<typeof useBGCWebhookStats>);
  Object.assign(global.navigator, {
    clipboard: {
      writeText: jest.fn().mockResolvedValue(undefined),
    },
  });
});

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('BGC Webhook Log page', () => {
  it('renders logs and metadata', async () => {
    renderWithClient(<AdminBGCWebhookPage />);

    expect(
      await screen.findByRole('heading', { name: /background check webhook log/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Last 200 deliveries/i)).toBeInTheDocument();
    expect(screen.getByText(/report\.completed/)).toBeInTheDocument();
    expect(screen.queryByText(/Delivery ID copied/i)).not.toBeInTheDocument();
  });

  it('opens JSON drawer when requested', async () => {
    renderWithClient(<AdminBGCWebhookPage />);
    await userEvent.click(screen.getByRole('button', { name: /view json/i }));
    await waitFor(() => expect(screen.getByText(/Payload/i)).toBeInTheDocument());
    expect(screen.getAllByText(/report\.completed/).length).toBeGreaterThan(0);
  });

  it('copies delivery id', async () => {
    renderWithClient(<AdminBGCWebhookPage />);
    const copyButtons = screen.getAllByRole('button', { name: /copy delivery/i });
    const copyTarget = copyButtons[0];
    expect(copyTarget).toBeDefined();
    await userEvent.click(copyTarget!);
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('delivery-1'),
    );
  });
});
