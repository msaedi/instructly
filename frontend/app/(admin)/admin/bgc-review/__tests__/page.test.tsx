import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import AdminBGCReviewPage from '../page';
import { toast } from 'sonner';
import type { BGCInviteResponse } from '@/lib/api/bgc';
import { ApiProblemError } from '@/lib/api/fetch';
import type { UseMutationResult } from '@tanstack/react-query';
import type { BGCCaseItem, AdminInstructorDetail } from '../hooks';
import { useBGCRecheck, useBGCInvite } from '../hooks';

jest.mock('../hooks', () => {
  const actual = jest.requireActual('../hooks');
  return {
    ...actual,
    useBGCRecheck: jest.fn(),
    useBGCInvite: jest.fn(),
  };
});

const mockedUseBGCRecheck = useBGCRecheck as jest.MockedFunction<typeof useBGCRecheck>;
const mockedUseBGCInvite = useBGCInvite as jest.MockedFunction<typeof useBGCInvite>;

function makeRecheckMutation(
  overrides: Partial<UseMutationResult<BGCInviteResponse, Error, { id: string }, unknown>> = {},
): UseMutationResult<BGCInviteResponse, Error, { id: string }, unknown> {
  const base = {
    mutate: jest.fn(),
    mutateAsync: jest.fn(),
    isPending: false,
    reset: jest.fn(),
  } satisfies Partial<UseMutationResult<BGCInviteResponse, Error, { id: string }, unknown>>;
  return { ...base, ...overrides } as unknown as UseMutationResult<
    BGCInviteResponse,
    Error,
    { id: string },
    unknown
  >;
}

function makeInviteMutation(
  overrides: Partial<UseMutationResult<BGCInviteResponse, Error, { id: string }, unknown>> = {},
): UseMutationResult<BGCInviteResponse, Error, { id: string }, unknown> {
  const base = {
    mutate: jest.fn(),
    mutateAsync: jest.fn(async () => ({
      ok: true,
      status: 'pending',
      report_id: 'rpt_invite',
      already_in_progress: false,
    })),
    isPending: false,
    reset: jest.fn(),
  };
  return { ...base, ...overrides } as unknown as UseMutationResult<
    BGCInviteResponse,
    Error,
    { id: string },
    unknown
  >;
}

let reviewItems: BGCCaseItem[];
let pendingItems: BGCCaseItem[];
let canceledItem: BGCCaseItem;
let reviewDetail: AdminInstructorDetail;

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
    info: jest.fn(),
  },
}));

jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
}));

const originalFetch = global.fetch;
let clipboardWriteMock: jest.Mock;

function createJsonResponse(body: unknown, status = 200): Response {
  const contentType = status >= 400 ? 'application/problem+json' : 'application/json';
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? contentType : null),
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
    mockedUseBGCRecheck.mockReturnValue(
      makeRecheckMutation({
        mutateAsync: jest.fn(async ({ id }: { id: string }) => ({
          ok: true,
          status: 'pending',
          report_id: `rpt_${id}`,
          already_in_progress: false,
        } as BGCInviteResponse)),
      }),
    );
    mockedUseBGCInvite.mockReturnValue(makeInviteMutation());
    reviewItems = [
      {
        instructor_id: '01TEST0INSTRUCTOR',
        name: 'Review Instructor',
        email: 'review@example.com',
        bgc_status: 'review',
        bgc_report_id: 'rpt_test123',
        bgc_completed_at: null,
        bgc_eta: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
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
        bgc_valid_until: new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString(),
        bgc_expires_in_days: 45,
        bgc_is_expired: false,
      },
    ];

    pendingItems = [
      {
        instructor_id: '01TEST0PENDING',
        name: 'Pending Instructor',
        email: 'pending@example.com',
        bgc_status: 'pending',
        bgc_report_id: 'rpt_pending',
        bgc_completed_at: null,
        bgc_eta: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(),
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
        bgc_valid_until: null,
        bgc_expires_in_days: null,
        bgc_is_expired: false,
      },
    ];

    canceledItem = {
      instructor_id: '01TESTCANCELED',
      name: 'Canceled Instructor',
      email: 'canceled@example.com',
      bgc_status: 'canceled',
      bgc_report_id: 'rpt_canceled',
      bgc_completed_at: null,
      bgc_eta: null,
      created_at: new Date().toISOString(),
      updated_at: null,
      consent_recent: false,
      consent_recent_at: null,
      checkr_report_url: 'https://dashboard.checkr.com/reports/rpt_canceled',
      is_live: false,
      in_dispute: false,
      dispute_note: null,
      dispute_opened_at: null,
      dispute_resolved_at: null,
      bgc_valid_until: null,
      bgc_expires_in_days: null,
      bgc_is_expired: false,
    };

    reviewDetail = {
      id: '01TEST0INSTRUCTOR',
      name: 'Review Instructor',
      email: 'review@example.com',
      is_live: false,
      bgc_status: 'review',
      bgc_report_id: 'rpt_test123',
      bgc_completed_at: null,
      bgc_eta: reviewItems[0]?.bgc_eta ?? null,
      consent_recent_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: null,
      bgc_valid_until: new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString(),
      bgc_expires_in_days: 45,
      bgc_is_expired: false,
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
          items = [...reviewItems, ...pendingItems, canceledItem];
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

      if (url.match(/\/api\/instructors\/[^/]+\/bgc\/recheck/)) {
        const match = url.match(/\/api\/instructors\/([^/]+)\/bgc\/recheck/);
        const instructorId = match?.[1];
        if (instructorId) {
          const inviteTime = new Date().toISOString();
          reviewItems = reviewItems.map((item) =>
            item.instructor_id === instructorId
              ? {
                  ...item,
                  bgc_status: 'pending',
                  bgc_valid_until: null,
                  bgc_expires_in_days: null,
                  bgc_is_expired: false,
                  consent_recent: true,
                  consent_recent_at: inviteTime,
                }
              : item,
          );
          if (reviewDetail.id === instructorId) {
            reviewDetail = {
              ...reviewDetail,
              bgc_status: 'pending',
              bgc_valid_until: null,
              bgc_expires_in_days: null,
              bgc_is_expired: false,
              consent_recent_at: inviteTime,
            };
          }
        }
        return createJsonResponse({ ok: true, status: 'pending', report_id: 'rpt_new' });
      }

      return createJsonResponse({}, 404);
    }) as jest.Mock;

    (usePathname as jest.Mock).mockReturnValue('/admin/bgc-review');

    clipboardWriteMock = jest.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: clipboardWriteMock,
      },
    });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: clipboardWriteMock,
      },
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
    global.fetch = originalFetch;
    if ('clipboard' in navigator) {
      Reflect.deleteProperty(navigator, 'clipboard');
    }
    if ('clipboard' in window.navigator) {
      Reflect.deleteProperty(window.navigator, 'clipboard');
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

  it('shows ETA for pending cases in table and preview', async () => {
    const etaIso = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString();
    if (reviewItems[0]) {
      reviewItems[0] = { ...reviewItems[0], bgc_status: 'pending', bgc_eta: etaIso };
    }
    reviewDetail = {
      ...reviewDetail,
      bgc_status: 'pending',
      bgc_eta: etaIso,
    };
    const expectedEta = new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(new Date(etaIso));

    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');
    const tableEtaMatches = await screen.findAllByText(expectedEta);
    expect(tableEtaMatches.length).toBeGreaterThan(0);

    const user = userEvent.setup();
    const previewButton = screen.getByRole('button', { name: /review instructor/i });
    await user.click(previewButton);

    await screen.findByText(/Estimated completion/i);
    await waitFor(() => {
      expect(screen.getAllByText(expectedEta).length).toBeGreaterThan(1);
    });
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

  it('shows canceled cases in All view with guidance in preview', async () => {
    renderWithClient(<AdminBGCReviewPage />);
    await screen.findByText('Review Instructor');

    const user = userEvent.setup();
    const allButton = screen.getByRole('button', { name: /all/i });
    await user.click(allButton);

    const canceledTrigger = await screen.findByRole('button', { name: /canceled instructor/i });
    const row = canceledTrigger.closest('tr');
    expect(row).not.toBeNull();
    if (row) {
      expect(within(row).getAllByText(/canceled/i).length).toBeGreaterThan(0);
    }

    reviewDetail = {
      ...reviewDetail,
      id: canceledItem.instructor_id,
      name: canceledItem.name,
      email: canceledItem.email,
      bgc_status: 'canceled',
      bgc_valid_until: null,
      bgc_expires_in_days: null,
      bgc_is_expired: false,
    };

    await user.click(canceledTrigger);
    await screen.findByText(/Instructor Preview/i);
    await screen.findByText(/Report was canceled in Checkr/i);
  });

  it('handles dispute open and resolve flow', async () => {
    const user = userEvent.setup();
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const previewButton = screen.getByRole('button', { name: /review instructor/i });
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
    await screen.findByText(/Final adverse actions are paused until the dispute is resolved/i);

    const rejectButton = screen.getByRole('button', { name: /reject/i });
    expect(rejectButton).toBeDisabled();
    expect(rejectButton).toHaveAttribute('title', 'Final adverse actions cannot continue while a dispute is active');
    await waitFor(() => expect(openButton).toBeDisabled());
    await waitFor(() => expect(resolveButton).toBeEnabled());

    await user.clear(noteField);
    await user.type(noteField, 'Verification corrected');

    await user.click(resolveButton);

    await waitFor(() => expect((toast.success as jest.Mock)).toHaveBeenCalledWith('Dispute resolved'));
    await waitFor(() => expect(screen.queryByText('In dispute')).not.toBeInTheDocument());
    await waitFor(() => expect(rejectButton).toBeEnabled());
  });

  it('allows copying identifiers and email from preview', async () => {
    const user = userEvent.setup();
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const writeSpy = jest
      .spyOn(navigator.clipboard, 'writeText')
      .mockResolvedValue(undefined as unknown as void);

    const previewButton = screen.getByRole('button', { name: /review instructor/i });
    await user.click(previewButton);

    await screen.findByText(/Instructor Preview/i);

    const copyIdButton = await screen.findByRole('button', { name: /copy id/i });
    await user.click(copyIdButton);

    await waitFor(() => expect(writeSpy).toHaveBeenCalledWith('01TEST0INSTRUCTOR'));
    await waitFor(() =>
      expect((toast.success as jest.Mock)).toHaveBeenCalledWith('Instructor ID copied to clipboard'),
    );

    writeSpy.mockClear();
    (toast.success as jest.Mock).mockClear();

    const copyEmailButton = await screen.findByRole('button', { name: /copy email/i });
    await user.click(copyEmailButton);

    await waitFor(() => expect(writeSpy).toHaveBeenCalledWith('review@example.com'));
    await waitFor(() =>
      expect((toast.success as jest.Mock)).toHaveBeenCalledWith('Email copied to clipboard'),
    );
  });

  it('surfaces validity info and allows triggering a re-check', async () => {
    const expiredDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    reviewDetail = {
      ...reviewDetail,
      bgc_status: 'passed',
      bgc_is_expired: true,
      bgc_valid_until: expiredDate,
      bgc_expires_in_days: null,
      consent_recent_at: null,
    };
    if (reviewItems[0]) {
      reviewItems[0] = {
        ...reviewItems[0],
        bgc_status: 'passed',
        bgc_is_expired: true,
        bgc_valid_until: expiredDate,
        bgc_expires_in_days: null,
        consent_recent: false,
        consent_recent_at: null,
      };
    }

    const mutateAsync = jest.fn(async ({ id }: { id: string }) => ({
      ok: true,
      status: 'pending',
      report_id: `rpt_${id}`,
      already_in_progress: false,
    } as BGCInviteResponse));
    mockedUseBGCRecheck.mockReturnValue(makeRecheckMutation({ mutateAsync }));

    const user = userEvent.setup();
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const previewButton = screen.getByRole('button', { name: /review instructor/i });
    await user.click(previewButton);

    await screen.findByText(/Instructor Preview/i);
    await screen.findByText(/Valid until/i);

    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    expect(recheckButton).toBeEnabled();

    await user.click(recheckButton);

    await waitFor(() =>
      expect((toast.success as jest.Mock)).toHaveBeenCalledWith('Background check re-check requested'),
    );
    expect(mutateAsync).toHaveBeenCalledWith({ id: '01TEST0INSTRUCTOR' });
  });

  it('disables re-check when consent is missing', async () => {
    const expiredDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    reviewDetail = {
      ...reviewDetail,
      bgc_status: 'passed',
      bgc_is_expired: true,
      bgc_valid_until: expiredDate,
      bgc_expires_in_days: null,
      consent_recent_at: null,
    };
    if (reviewItems[0]) {
      reviewItems[0] = {
        ...reviewItems[0],
        bgc_status: 'passed',
        bgc_is_expired: true,
        bgc_valid_until: expiredDate,
        bgc_expires_in_days: null,
        consent_recent: false,
        consent_recent_at: null,
      };
    }

    const consentError = new ApiProblemError(
      {
        type: 'about:blank',
        title: 'Consent required',
        status: 400,
        detail: 'FCRA consent required',
        code: 'bgc_consent_required',
      },
      { status: 400 } as Response,
    );
    const mutateAsync = jest.fn(async () => {
      throw consentError;
    });
    mockedUseBGCRecheck.mockReturnValue(makeRecheckMutation({ mutateAsync }));

    const user = userEvent.setup();
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const previewButton = screen.getByRole('button', { name: /review instructor/i });
    await user.click(previewButton);
    await screen.findByText(/Instructor Preview/i);

    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await user.click(recheckButton);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    await waitFor(() =>
      expect((toast.info as jest.Mock)).toHaveBeenCalledWith('Instructor must consent before re-check.'),
    );
    await waitFor(() => expect(recheckButton).toBeDisabled());
  });

  it('disables re-check on rate limit and shows tooltip copy', async () => {
    const expiredDate = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
    reviewDetail = {
      ...reviewDetail,
      bgc_status: 'passed',
      bgc_is_expired: true,
      bgc_valid_until: expiredDate,
      bgc_expires_in_days: null,
      consent_recent_at: new Date().toISOString(),
    };
    if (reviewItems[0]) {
      reviewItems[0] = {
        ...reviewItems[0],
        bgc_status: 'passed',
        bgc_is_expired: true,
        bgc_valid_until: expiredDate,
        bgc_expires_in_days: null,
        consent_recent: true,
        consent_recent_at: new Date().toISOString(),
      };
    }

    const rateLimitError = new ApiProblemError(
      {
        type: 'about:blank',
        title: 'Rate limited',
        status: 429,
        detail: 'Too many requests',
        code: 'bgc_recheck_rate_limited',
      },
      { status: 429 } as Response,
    );
    const mutateAsync = jest.fn(async () => {
      throw rateLimitError;
    });
    mockedUseBGCRecheck.mockReturnValue(makeRecheckMutation({ mutateAsync }));

    const user = userEvent.setup();
    renderWithClient(<AdminBGCReviewPage />);

    await screen.findByText('Review Instructor');

    const previewButton = screen.getByRole('button', { name: /review instructor/i });
    await user.click(previewButton);
    await screen.findByText(/Instructor Preview/i);

    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await user.click(recheckButton);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    await waitFor(() =>
      expect((toast.info as jest.Mock)).toHaveBeenCalledWith('Too many re-checks. Try later.'),
    );
    await waitFor(() => expect(recheckButton).toBeDisabled());
    await waitFor(() => expect(recheckButton).toHaveAttribute('title', 'Try later'));
  });
});
