import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import ReferralsAdminClient from '../ReferralsAdminClient';
import { usePathname } from 'next/navigation';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const originalFetch = global.fetch;

function createJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
    },
    json: async () => body,
  } as unknown as Response;
}

jest.mock('@/hooks/useAdminAuth', () => ({
  useAdminAuth: () => ({ isAdmin: true, isLoading: false }),
}));

const mockLogout = jest.fn();

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ logout: mockLogout }),
}));

describe('AdminReferralsPage', () => {
  beforeEach(() => {
    (usePathname as unknown as jest.Mock).mockReturnValue('/admin/referrals');
    mockLogout.mockReset();
    global.fetch = jest.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/admin/bgc/review/count')) {
        return Promise.resolve(createJsonResponse({ count: 3 }));
      }
      if (url.includes('/api/admin/referrals/health')) {
        return Promise.resolve(
          createJsonResponse({
            workers_alive: 3,
            workers: ['celery@worker-1', 'celery@worker-2', 'celery@worker-3'],
            backlog_pending_due: 5,
            pending_total: 12,
            unlocked_total: 8,
            void_total: 1,
          }),
        );
      }
      if (url.includes('/api/admin/referrals/summary')) {
        return Promise.resolve(
          createJsonResponse({
            counts_by_status: {
              pending: 12,
              unlocked: 8,
              redeemed: 20,
              void: 1,
            },
            cap_utilization_percent: 42.5,
            top_referrers: [
              {
                user_id: 'referrer-1',
                count: 7,
                code: 'ALPHA1',
              },
            ],
            clicks_24h: 15,
            attributions_24h: 4,
          }),
        );
      }

      return Promise.resolve(createJsonResponse({}, 404));
    }) as typeof fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it('renders unlocker health and summary metrics', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ReferralsAdminClient />
      </QueryClientProvider>,
    );

    const fetchMock = global.fetch as jest.Mock;
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(3));

    expect(screen.getByRole('link', { name: /instainstru/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Referrals Admin' })).toBeInTheDocument();
    expect(
      screen.getByText('Unlocker health, backlog, and top referrers.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument();
    const refreshButton = screen.getByRole('button', { name: /refresh data/i });
    expect(refreshButton).toBeInTheDocument();

    await screen.findByText(/celery@worker-1/);

    const workersCard = screen.getByText('Workers Alive').closest('div');
    expect(workersCard).toHaveTextContent('3');
    const backlogCard = screen.getByText('Backlog Pending Due').closest('div');
    expect(backlogCard).toHaveTextContent('5');
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByText('Unlocked')).toBeInTheDocument();
    expect(screen.getByText('Void')).toBeInTheDocument();
    expect(screen.getByText('referrer-1')).toBeInTheDocument();
    expect(screen.getByText('ALPHA1')).toBeInTheDocument();

    const initialCalls = fetchMock.mock.calls.length;
    const user = userEvent.setup();
    await user.click(refreshButton);
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCalls));
  });
});
