import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import AdminBGCReviewPage from '../page';
import { toast } from 'sonner';
import type { BGCCaseItem, AdminInstructorDetail } from '../hooks';

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
    let reviewItems: BGCCaseItem[] = [
      {
        instructor_id: '01TEST0INSTRUCTOR',
        name: 'Review Instructor',
        email: 'review@example.com',
        bgc_status: 'review',
        bgc_report_id: 'rpt_test123',
        bgc_completed_at: null,
        created_at: new Date().toISOString(),
        updated_at: null,
        consent_recent: true,
        consent_recent_at: new Date().toISOString(),
        checkr_report_url: 'https://dashboard.checkr.com/reports/rpt_test123',
        is_live: false,
        in_dispute: false,
        dispute_note: null,
        dispute_opened_at: null,
        dispute_resolved_at: null,
      },
    ];

    const pendingItems: BGCCaseItem[] = [
      {
        instructor_id: '01TEST0PENDING',
        name: 'Pending Instructor',
        email: 'pending@example.com',
        bgc_status: 'pending',
        bgc_report_id: 'rpt_pending',
        bgc_completed_at: null,
        created_at: new Date().toISOString(),
        updated_at: null,
        consent_recent: false,
        consent_recent_at: null,
        checkr_report_url: null,
        is_live: false,
        in_dispute: false,
        dispute_note: null,
        dispute_opened_at: null,
        dispute_resolved_at: null,
      },
    ];

    let reviewDetail: AdminInstructorDetail = {
      id: '01TEST0INSTRUCTOR',
      name: 'Review Instructor',
      email: 'review@example.com',
      is_live: false,
      bgc_status: 'review',
      bgc_report_id: 'rpt_test123',
      bgc_completed_at: null,
      consent_recent_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: null,
      bgc_in_dispute: false,
      bgc_dispute_note: null,
      bgc_dispute_opened_at: null,
      bgc_dispute_resolved_at: null,
    };

    global.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();

      if (url.includes('/api/admin/bgc/counts')) {
        return createJsonResponse({ review: reviewItems.length, pending: pendingItems.length });
      }

      if (url.includes('/api/admin/bgc/cases')) {
        const requestUrl = new URL(url, 'http://localhost');
        const status = requestUrl.searchParams.get('status') ?? 'review';
        let items;
        if (status === 'pending') {
          items = pendingItems;
        } else if (status === 'all') {
          items = [...reviewItems, ...pendingItems];
        } else {
          items = reviewItems;
        }
        return createJsonResponse({ items, next_cursor: null });
      }

      if (url.includes('/api/admin/instructors/')) {
        return createJsonResponse(reviewDetail);
      }

      if (url.includes('/dispute/open')) {
        const match = url.match(/\/api\/admin\/bgc\/([^/]+)\/dispute\/open/);
        const notePayload = (() => {
          if (init && typeof init.body === 'string') {
            try {
              const parsed = JSON.parse(init.body);
              return typeof parsed.note === 'string' ? parsed.note : null;
            } catch {
              return null;
            }
          }
          return null;
        })();
        const openedAt = new Date().toISOString();
        if (match?.[1]) {
          reviewItems = reviewItems.map((item) =>
            item.instructor_id === match[1]
              ? {
                  ...item,
                  in_dispute: true,
                  dispute_note: notePayload,
                  dispute_opened_at: openedAt,
                  dispute_resolved_at: null,
                }
              : item,
          );
          reviewDetail = {
            ...reviewDetail,
            bgc_in_dispute: true,
            bgc_dispute_note: notePayload,
            bgc_dispute_opened_at: openedAt,
            bgc_dispute_resolved_at: null,
          };
        }
        return createJsonResponse({
          ok: true,
          in_dispute: true,
          dispute_note: notePayload,
          dispute_opened_at: openedAt,
          dispute_resolved_at: null,
        });
      }

      if (url.includes('/dispute/resolve')) {
        const match = url.match(/\/api\/admin\/bgc\/([^/]+)\/dispute\/resolve/);
        const notePayload = (() => {
          if (init && typeof init.body === 'string') {
            try {
              const parsed = JSON.parse(init.body);
              return typeof parsed.note === 'string' ? parsed.note : null;
            } catch {
              return null;
            }
          }
          return null;
        })();
        const resolvedAt = new Date().toISOString();
        if (match?.[1]) {
          reviewItems = reviewItems.map((item) =>
            item.instructor_id === match[1]
              ? {
                  ...item,
                  in_dispute: false,
                  dispute_note: notePayload,
                  dispute_resolved_at: resolvedAt,
                }
              : item,
          );
          reviewDetail = {
            ...reviewDetail,
            bgc_in_dispute: false,
            bgc_dispute_note: notePayload,
            bgc_dispute_resolved_at: resolvedAt,
          };
        }
        return createJsonResponse({
          ok: true,
          in_dispute: false,
          dispute_note: notePayload,
          dispute_opened_at: reviewDetail.bgc_dispute_opened_at,
          dispute_resolved_at: resolvedAt,
        });
      }

      if (url.includes('/override')) {
        reviewItems = [];
        return createJsonResponse({ ok: true, new_status: 'passed' });
      }

      return createJsonResponse({}, 404);
    }) as jest.Mock;

    (usePathname as jest.Mock).mockReturnValue('/admin/bgc-review');

    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: jest.fn(),
      },
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
    global.fetch = originalFetch;
    if ('clipboard' in navigator) {
      Reflect.deleteProperty(navigator, 'clipboard');
    }
  });

  it('renders review queue and allows approving a case', async () => {
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const approveButton = screen.getByRole('button', { name: /approve/i });
    const user = userEvent.setup();
    await user.click(approveButton);

    await waitFor(() => expect((toast.success as jest.Mock)).toHaveBeenCalled());
    await screen.findByText('No cases match the current filters.');
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument(),
    );

    const fetchMock = global.fetch as jest.Mock;
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/admin/bgc/01TEST0INSTRUCTOR/override'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('switches pending filter and hides adjudication buttons', async () => {
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const pendingButton = screen.getByRole('button', { name: /pending/i });
    const user = userEvent.setup();
    await user.click(pendingButton);

    await screen.findByText('Pending Instructor');

    expect(screen.queryByText('Review Instructor')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
  });

  it('handles dispute open and resolve flow', async () => {
    const user = userEvent.setup();
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const previewButton = screen.getByTitle(/profile not public/i);
    await user.click(previewButton);

    await screen.findByText(/Instructor Preview/i);

    const openButton = await screen.findByRole('button', { name: /open dispute/i });
    const resolveButton = screen.getByRole('button', { name: /resolve dispute/i });
    expect(openButton).toBeEnabled();
    expect(resolveButton).toBeDisabled();

    const noteField = screen.getByPlaceholderText(/Document dispute context/i);
    await user.type(noteField, 'Candidate requested clarification');

    await user.click(openButton);

    await waitFor(() => expect((toast.success as jest.Mock)).toHaveBeenCalledWith('Dispute opened'));
    await waitFor(() => expect(screen.getAllByText('In dispute').length).toBeGreaterThan(0));

    const rejectButton = screen.getByRole('button', { name: /reject/i });
    expect(rejectButton).toBeDisabled();
    await waitFor(() => expect(openButton).toBeDisabled());
    await waitFor(() => expect(resolveButton).toBeEnabled());

    await user.clear(noteField);
    await user.type(noteField, 'Verification corrected');

    await user.click(resolveButton);

    await waitFor(() => expect((toast.success as jest.Mock)).toHaveBeenCalledWith('Dispute resolved'));
    await waitFor(() => expect(screen.queryByText('In dispute')).not.toBeInTheDocument());
    await waitFor(() => expect(rejectButton).toBeEnabled());
  });
});
