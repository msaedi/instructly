import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import AdminReferralsPage from '../page';

const originalFetch = global.fetch;

jest.mock('@/hooks/useAdminAuth', () => ({
  useAdminAuth: () => ({ isAdmin: true, isLoading: false }),
}));

describe('AdminReferralsPage', () => {
  beforeEach(() => {
    global.fetch = jest.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/api/admin/referrals/health')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            workers_alive: 3,
            workers: ['celery@worker-1', 'celery@worker-2', 'celery@worker-3'],
            backlog_pending_due: 5,
            pending_total: 12,
            unlocked_total: 8,
            void_total: 1,
          }),
        } as unknown as Response);
      }
      if (url.includes('/api/admin/referrals/summary')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
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
        } as unknown as Response);
      }

      return Promise.resolve({
        ok: false,
        status: 404,
        json: async () => ({}),
      } as unknown as Response);
    }) as typeof fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it('renders unlocker health and summary metrics', async () => {
    render(<AdminReferralsPage />);

    const fetchMock = global.fetch as jest.Mock;
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

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
  });
});
