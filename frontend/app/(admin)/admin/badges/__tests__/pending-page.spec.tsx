import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdminPendingBadgesPage from '../pending/page';

jest.mock('@/hooks/useAdminAuth', () => ({
  useAdminAuth: () => ({ isAdmin: true, isLoading: false }),
}));

const mockLogout = jest.fn();
jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: () => ({ logout: mockLogout }),
}));

const listPendingAwards = jest.fn();
const confirmAward = jest.fn();
const revokeAward = jest.fn();

jest.mock('@/services/api/badges', () => ({
  badgesApi: {
    listPendingAwards: (...args: unknown[]) => listPendingAwards(...args),
    confirmAward: (...args: unknown[]) => confirmAward(...args),
    revokeAward: (...args: unknown[]) => revokeAward(...args),
  },
}));

type PartialAward = {
  award_id?: string;
  badge?: { name: string; slug: string };
  student?: { id: string; email?: string | null; display_name?: string | null };
  status?: 'pending' | 'confirmed' | 'revoked';
};

function createJsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null),
    },
    json: async () => body,
    clone: () => createJsonResponse(body, status),
  } as unknown as Response;
}

const createAward = (overrides: PartialAward = {}) => ({
  award_id: overrides.award_id ?? 'award-1',
  status: overrides.status ?? 'pending',
  awarded_at: '2024-01-01T00:00:00Z',
  hold_until: '2024-01-08T00:00:00Z',
  badge: overrides.badge ?? { name: 'Explorer Badge', slug: 'explorer' },
  student:
    overrides.student ??
    ({
      id: 'student-1',
      email: 'student@example.com',
      display_name: 'Tina Test',
    } as const),
});

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AdminPendingBadgesPage />
    </QueryClientProvider>,
  );
}

describe('AdminPendingBadgesPage', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    listPendingAwards.mockReset();
    confirmAward.mockReset();
    revokeAward.mockReset();
    mockLogout.mockReset();
    global.fetch = jest.fn(() => Promise.resolve(createJsonResponse({}))) as typeof fetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it('renders shared admin header with brand and logout', async () => {
    listPendingAwards.mockResolvedValue({
      items: [],
      total: 0,
      next_offset: null,
    });

    renderPage();

    await screen.findByRole('heading', { name: 'Pending Awards' });
    expect(screen.getByRole('link', { name: /instainstru/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Badge Reviews' })).toBeInTheDocument();
    expect(
      screen.getAllByText('Review badges before they are confirmed for students.').length
    ).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument();
  });

  it('renders rows and confirms an award', async () => {
    const pendingAward = createAward();
    listPendingAwards.mockResolvedValue({
      items: [pendingAward],
      total: 1,
      next_offset: null,
    });
    confirmAward.mockResolvedValue({ ...pendingAward, status: 'confirmed' });

    renderPage();

    await screen.findByText('Explorer Badge');
    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    await userEvent.click(confirmButton);

    await waitFor(() => {
      expect(confirmAward).toHaveBeenCalledWith('award-1', expect.anything());
    });
    await waitFor(() => {
      const row = screen.getByText('Explorer Badge').closest('tr');
      expect(row).toHaveTextContent(/confirmed/i);
    });
  });

  it('revokes an award', async () => {
    const pendingAward = createAward({ award_id: 'award-2', badge: { name: 'Top Student', slug: 'top_student' } });
    listPendingAwards.mockResolvedValue({
      items: [pendingAward],
      total: 1,
      next_offset: null,
    });
    revokeAward.mockResolvedValue({ ...pendingAward, status: 'revoked' });

    renderPage();

    await screen.findByText('Top Student');
    const revokeButton = screen.getByRole('button', { name: /revoke/i });
    await userEvent.click(revokeButton);

    await waitFor(() => {
      expect(revokeAward).toHaveBeenCalledWith('award-2', expect.anything());
    });
    await screen.findByText(/revoked/i);
  });

  it('requests next page when pagination advances', async () => {
    const firstPage = {
      items: [createAward()],
      total: 2,
      next_offset: 50,
    };
    const secondPage = {
      items: [createAward({ award_id: 'award-3', badge: { name: 'Year One', slug: 'year_one_learner' } })],
      total: 2,
      next_offset: null,
    };

    listPendingAwards.mockResolvedValueOnce(firstPage).mockResolvedValueOnce(secondPage);

    renderPage();

    await screen.findByText('Explorer Badge');
    await userEvent.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() => {
      expect(listPendingAwards).toHaveBeenCalledTimes(2);
    });

    const lastCallArgs = listPendingAwards.mock.calls[1][0];
    expect(lastCallArgs).toMatchObject({ offset: 50 });
    await screen.findByText('Year One');
  });
});
