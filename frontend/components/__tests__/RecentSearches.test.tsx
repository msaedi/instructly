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

  it('does not fetch searches while auth is loading', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: true });

    const { container } = render(<RecentSearches />);

    // Should show nothing because still loading (loading=true initially)
    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
    expect(getRecentSearchesMock).not.toHaveBeenCalled();
  });

  it('logs error when loadGuestSearches fails', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    const mockError = new Error('LocalStorage full');
    getRecentSearchesMock.mockRejectedValue(mockError);

    const { container } = render(<RecentSearches />);

    await waitFor(() => {
      expect(logger.error).toHaveBeenCalledWith('Error loading guest searches', mockError);
    });
    // Should render nothing when guest fetch fails (no searches loaded)
    expect(container.firstChild).toBeNull();
  });

  it('logs error and sets error state when fetchRecentSearches fails', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false });
    const mockError = new Error('Network error');
    getRecentSearchesMock.mockRejectedValue(mockError);

    const { container } = render(<RecentSearches />);

    await waitFor(() => {
      expect(logger.error).toHaveBeenCalledWith('Error fetching recent searches', mockError);
    });
    // Should render nothing when fetch fails (empty searches)
    expect(container.firstChild).toBeNull();
  });

  it('refetches guest searches on delete failure', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Drums', search_type: 'lesson', results_count: 5 },
    ]);
    deleteSearchMock.mockResolvedValue(false);

    const user = userEvent.setup();
    render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Drums')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /remove search/i }));

    await waitFor(() => {
      expect(deleteSearchMock).toHaveBeenCalledWith('1', false);
      // Should call getRecentSearches again (with false = guest) to restore state
      expect(getRecentSearchesMock).toHaveBeenCalledTimes(2);
    });
  });

  it('logs error when delete throws an exception', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Yoga', search_type: 'lesson', results_count: 3 },
    ]);
    const deleteError = new Error('Delete failed');
    deleteSearchMock.mockRejectedValue(deleteError);

    const user = userEvent.setup();
    render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Yoga')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /remove search/i }));

    await waitFor(() => {
      expect(logger.error).toHaveBeenCalledWith('Error deleting search', deleteError);
    });
  });

  it('does not attach storage listener when auth is loading', async () => {
    const addEventListenerSpy = jest.spyOn(window, 'addEventListener');
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: true });

    render(<RecentSearches />);

    // Should not attach storage/guestSearchUpdated listeners
    expect(addEventListenerSpy).not.toHaveBeenCalledWith('storage', expect.any(Function));
    expect(addEventListenerSpy).not.toHaveBeenCalledWith('guestSearchUpdated', expect.any(Function));

    addEventListenerSpy.mockRestore();
  });

  it('refreshes on storage event for guest users', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Cello', search_type: 'lesson', results_count: 1 },
    ]);

    render(<RecentSearches />);

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new Event('storage'));

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalledTimes(2));
  });

  it('refreshes on searchHistoryUpdated event for authenticated users', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Violin', search_type: 'lesson', results_count: 1 },
    ]);

    render(<RecentSearches />);

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalledTimes(1));
    window.dispatchEvent(new Event('searchHistoryUpdated'));

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalledTimes(2));
  });

  it('does not attach searchHistoryUpdated listener for guest users', async () => {
    const addEventListenerSpy = jest.spyOn(window, 'addEventListener');
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([]);

    render(<RecentSearches />);

    await waitFor(() => expect(getRecentSearchesMock).toHaveBeenCalled());

    const searchHistoryCalls = addEventListenerSpy.mock.calls.filter(
      ([event]) => event === 'searchHistoryUpdated'
    );
    expect(searchHistoryCalls).toHaveLength(0);

    addEventListenerSpy.mockRestore();
  });

  it('hides results_count label when results_count is null', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Cooking', search_type: 'lesson', results_count: null },
    ]);

    render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Cooking')).toBeInTheDocument());
    // Should not show results count text
    expect(screen.queryByText(/result/i)).not.toBeInTheDocument();
  });

  it('uses fallback date for missing timestamp fields', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      {
        id: '1',
        search_query: 'Flute',
        search_type: 'lesson',
        results_count: 0,
        last_searched_at: '',
        first_searched_at: '',
      },
    ]);

    render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Flute')).toBeInTheDocument());
    // Should render without crashing; falls back to new Date().toISOString()
    expect(screen.getByText('0 results')).toBeInTheDocument();
  });

  it('uses id fallback when item.id is falsy', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      {
        id: null,
        search_query: 'Sax',
        search_type: 'lesson',
        results_count: 1,
      },
    ]);

    render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Sax')).toBeInTheDocument());
  });

  it('handles singular result count correctly', async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Harp', search_type: 'lesson', results_count: 1 },
    ]);

    render(<RecentSearches />);

    await waitFor(() => {
      expect(screen.getByText('Harp')).toBeInTheDocument();
      expect(screen.getByText('1 result')).toBeInTheDocument();
    });
  });

  it('cleans up event listeners on unmount for guest users', async () => {
    const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');
    useAuthMock.mockReturnValue({ isAuthenticated: false, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Oboe', search_type: 'lesson', results_count: 1 },
    ]);

    const { unmount } = render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Oboe')).toBeInTheDocument());

    unmount();

    const storageCalls = removeEventListenerSpy.mock.calls.filter(
      ([event]) => event === 'storage'
    );
    const guestCalls = removeEventListenerSpy.mock.calls.filter(
      ([event]) => event === 'guestSearchUpdated'
    );
    expect(storageCalls.length).toBeGreaterThanOrEqual(1);
    expect(guestCalls.length).toBeGreaterThanOrEqual(1);

    removeEventListenerSpy.mockRestore();
  });

  it('cleans up searchHistoryUpdated listener on unmount for authenticated users', async () => {
    const removeEventListenerSpy = jest.spyOn(window, 'removeEventListener');
    useAuthMock.mockReturnValue({ isAuthenticated: true, isLoading: false });
    getRecentSearchesMock.mockResolvedValue([
      { id: '1', search_query: 'Trumpet', search_type: 'lesson', results_count: 1 },
    ]);

    const { unmount } = render(<RecentSearches />);

    await waitFor(() => expect(screen.getByText('Trumpet')).toBeInTheDocument());

    unmount();

    const searchHistoryCalls = removeEventListenerSpy.mock.calls.filter(
      ([event]) => event === 'searchHistoryUpdated'
    );
    expect(searchHistoryCalls.length).toBeGreaterThanOrEqual(1);

    removeEventListenerSpy.mockRestore();
  });
});
