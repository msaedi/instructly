import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import AdminBGCReviewPage from '../page';
import { toast } from 'sonner';

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

jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
}));

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

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('AdminBGCReviewPage', () => {
  beforeEach(() => {
    let listCall = 0;
    let countCall = 0;

    global.fetch = jest.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();

      if (url.includes('/api/admin/bgc/review/count')) {
        countCall += 1;
        return createJsonResponse({ count: countCall === 1 ? 1 : 0 });
      }

      if (url.includes('/api/admin/bgc/review?')) {
        listCall += 1;
        if (listCall === 1) {
          return createJsonResponse({
            items: [
              {
                instructor_id: '01TEST0INSTRUCTOR',
                name: 'Review Instructor',
                email: 'review@example.com',
                bgc_status: 'review',
                bgc_report_id: 'rpt_test123',
                bgc_completed_at: null,
                created_at: new Date().toISOString(),
                consented_at_recent: true,
                checkr_report_url: 'https://dashboard.checkr.com/reports/rpt_test123',
              },
            ],
            next_cursor: null,
          });
        }
        return createJsonResponse({ items: [], next_cursor: null });
      }

      if (url.includes('/override')) {
        return createJsonResponse({ ok: true, new_status: 'passed' });
      }

      return createJsonResponse({}, 404);
    }) as jest.Mock;

    (usePathname as jest.Mock).mockReturnValue('/admin/bgc-review');

    Object.assign(navigator, {
      clipboard: {
        writeText: jest.fn(),
      },
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
    global.fetch = originalFetch;
  });

  it('renders review queue and allows approving a case', async () => {
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const approveButton = screen.getByRole('button', { name: /approve/i });
    const user = userEvent.setup();
    await user.click(approveButton);

    await waitFor(() => expect((toast.success as jest.Mock)).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByText('Review Instructor')).not.toBeInTheDocument(),
    );

    const fetchMock = global.fetch as jest.Mock;
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/admin/bgc/01TEST0INSTRUCTOR/override'),
      expect.objectContaining({ method: 'POST' }),
    );
  });
});
