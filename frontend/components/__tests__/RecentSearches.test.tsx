import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RecentSearches } from '../RecentSearches';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { getRecentSearches, deleteSearch } from '@/lib/searchTracking';
import { logger } from '@/lib/logger';

jest.mock('@/features/shared/hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/lib/searchTracking', () => ({
  getRecentSearches: jest.fn(),
  deleteSearch: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: { error: jest.fn() },
}));

const useAuthMock = useAuth as jest.Mock;
const getRecentSearchesMock = getRecentSearches as jest.Mock;
const deleteSearchMock = deleteSearch as jest.Mock;

const setupSessionStorage = () => {
  const storage: Record<string, string> = {};
  Object.defineProperty(window, 'sessionStorage', {
    value: {
      setItem: jest.fn((key: string, value: string) => {
        storage[key] = value;
      }),
      getItem: jest.fn((key: string) => storage[key] ?? null),
      removeItem: jest.fn((key: string) => {
        delete storage[key];
      }),
      clear: jest.fn(() => {
        Object.keys(storage).forEach((key) => delete storage[key]);
      }),
    },
    configurable: true,
  });
};

describe('RecentSearches', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupSessionStorage();
  });

  it('renders guest searches and results counts', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Guitar', search_type: 'lesson', results_count: 2 },
    ]);

    render(<RecentSearches />);

    await waitFor(() => {
      expect(screen.getByText('Your Recent Searches')).toBeInTheDocument();
    });
    expect(getRecentSearchesMock).toHaveBeenCalledWith(false, 3);
    expect(screen.getByText('Guitar')).toBeInTheDocument();
    expect(screen.getByText('2 results')).toBeInTheDocument();
  });

  it('renders authenticated searches', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '9', search_query: 'Piano', search_type: 'lesson', results_count: 1 },
    ]);

    render(<RecentSearches />);

    await waitFor(() => {
      expect(screen.getByText('Piano')).toBeInTheDocument();
    });
    expect(getRecentSearchesMock).toHaveBeenCalledWith(true, 3);
    expect(screen.getByText('1 result')).toBeInTheDocument();
  });

  it('stores navigation origin when a search link is clicked', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Drums', search_type: 'lesson', results_count: 3 },
    ]);
    window.history.pushState({}, '', '/home');

    const user = userEvent.setup();
    render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Drums')).toBeInTheDocument());
    const drumsLink = screen.getByRole('link', { name: /drums/i });
    drumsLink.addEventListener('click', (event) => event.preventDefault());
    await user.click(drumsLink);

    expect(window.sessionStorage.setItem).toHaveBeenCalledWith('navigationFrom', '/home');
  });

  it('deletes a search and falls back to refetch on failure', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Violin', search_type: 'lesson', results_count: 1 },
    ]);
    deleteSearchMock.mockResolvedValue(false);

    const user = userEvent.setup();
    render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Violin')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /remove search/i }));

    await waitFor(() => {
      expect(deleteSearchMock).toHaveBeenCalledWith('1', true);
      expect(getRecentSearchesMock).toHaveBeenCalledTimes(2);
    });
  });

  it('updates guest searches on custom events', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Bass', search_type: 'lesson', results_count: 1 },
    ]);

    render(<RecentSearches />);

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new Event('guestSearchUpdated'));

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalledTimes(2));
  });

  it('renders nothing when there are no searches', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([]);

    const { container } = render(<RecentSearches />);

    await waitFor(() => {
      expect(getRecentSearchesMock).toHaveBeenCalled();
    });
    expect(container.firstChild).toBeNull();
    expect(logger.error).not.toHaveBeenCalled();
  });
});
