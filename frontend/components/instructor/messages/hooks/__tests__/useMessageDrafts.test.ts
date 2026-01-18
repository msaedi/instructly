import { renderHook, act } from '@testing-library/react';
import { useMessageDrafts } from '../useMessageDrafts';
import { DRAFT_COOKIE_NAME, COMPOSE_THREAD_ID } from '../../constants';

// Store for mock document.cookie
let mockCookies: Record<string, string> = {};

// Mock document.cookie
const originalDescriptor = Object.getOwnPropertyDescriptor(document, 'cookie');

beforeAll(() => {
  Object.defineProperty(document, 'cookie', {
    get: () => {
      return Object.entries(mockCookies)
        .map(([key, value]) => `${key}=${value}`)
        .join('; ');
    },
    set: (value: string) => {
      const [cookiePart] = value.split(';');
      const [name, ...valueParts] = (cookiePart || '').split('=');
      const cookieValue = valueParts.join('=');

      if (name) {
        // Check for max-age=0 (deletion) - handles empty value deletion
        if (value.includes('max-age=0')) {
          delete mockCookies[name];
        } else if (cookieValue) {
          mockCookies[name] = cookieValue;
        }
      }
    },
    configurable: true,
  });
});

afterAll(() => {
  if (originalDescriptor) {
    Object.defineProperty(document, 'cookie', originalDescriptor);
  }
});

describe('useMessageDrafts', () => {
  beforeEach(() => {
    mockCookies = {};
  });

  it('initializes with empty drafts when no cookie exists', () => {
    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.draftsByThread).toEqual({});
  });

  it('loads drafts from cookie on initialization', () => {
    const storedDrafts = { 'thread-1': 'Draft message 1', 'thread-2': 'Draft message 2' };
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify(storedDrafts));

    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.draftsByThread).toEqual(storedDrafts);
  });

  it('getDraftKey returns thread ID when provided', () => {
    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.getDraftKey('thread-123')).toBe('thread-123');
  });

  it('getDraftKey returns COMPOSE_THREAD_ID when thread is null', () => {
    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.getDraftKey(null)).toBe(COMPOSE_THREAD_ID);
  });

  it('getCurrentDraft returns draft for thread', () => {
    const storedDrafts = { 'thread-1': 'Hello draft' };
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify(storedDrafts));

    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.getCurrentDraft('thread-1')).toBe('Hello draft');
  });

  it('getCurrentDraft returns empty string for non-existent thread', () => {
    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.getCurrentDraft('non-existent')).toBe('');
  });

  it('getCurrentDraft uses COMPOSE_THREAD_ID for null thread', () => {
    const storedDrafts = { [COMPOSE_THREAD_ID]: 'Compose draft' };
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify(storedDrafts));

    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.getCurrentDraft(null)).toBe('Compose draft');
  });

  it('updateDraft sets draft for thread', () => {
    const { result } = renderHook(() => useMessageDrafts());

    act(() => {
      result.current.updateDraft('thread-1', 'New draft content');
    });

    expect(result.current.draftsByThread['thread-1']).toBe('New draft content');
  });

  it('updateDraft persists to cookie', () => {
    const { result } = renderHook(() => useMessageDrafts());

    act(() => {
      result.current.updateDraft('thread-1', 'Persisted draft');
    });

    expect(mockCookies[DRAFT_COOKIE_NAME]).toBeDefined();
    const stored = JSON.parse(decodeURIComponent(mockCookies[DRAFT_COOKIE_NAME] || '{}'));
    expect(stored['thread-1']).toBe('Persisted draft');
  });

  it('updateDraft does not update when value unchanged', () => {
    const storedDrafts = { 'thread-1': 'Same value' };
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify(storedDrafts));

    const { result } = renderHook(() => useMessageDrafts());
    const initialDrafts = result.current.draftsByThread;

    act(() => {
      result.current.updateDraft('thread-1', 'Same value');
    });

    // Should return same reference since value didn't change
    expect(result.current.draftsByThread).toBe(initialDrafts);
  });

  it('clearDraft removes draft for thread', () => {
    const storedDrafts = { 'thread-1': 'To be cleared' };
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify(storedDrafts));

    const { result } = renderHook(() => useMessageDrafts());

    act(() => {
      result.current.clearDraft('thread-1');
    });

    expect(result.current.draftsByThread['thread-1']).toBe('');
  });

  it('clearDraft works for null thread (compose)', () => {
    const storedDrafts = { [COMPOSE_THREAD_ID]: 'Compose to clear' };
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify(storedDrafts));

    const { result } = renderHook(() => useMessageDrafts());

    act(() => {
      result.current.clearDraft(null);
    });

    expect(result.current.draftsByThread[COMPOSE_THREAD_ID]).toBe('');
  });

  it('clearDraft does nothing when draft does not exist', () => {
    const { result } = renderHook(() => useMessageDrafts());
    const initialDrafts = result.current.draftsByThread;

    act(() => {
      result.current.clearDraft('non-existent');
    });

    expect(result.current.draftsByThread).toBe(initialDrafts);
  });

  it('clears cookie when all drafts are empty', () => {
    const { result } = renderHook(() => useMessageDrafts());

    act(() => {
      result.current.updateDraft('thread-1', 'Draft');
    });

    act(() => {
      result.current.clearDraft('thread-1');
    });

    // Cookie should be cleared (max-age=0)
    expect(mockCookies[DRAFT_COOKIE_NAME]).toBeUndefined();
  });

  it('setDraftsByThread allows direct updates', () => {
    const { result } = renderHook(() => useMessageDrafts());

    act(() => {
      result.current.setDraftsByThread({
        'thread-a': 'Draft A',
        'thread-b': 'Draft B',
      });
    });

    expect(result.current.draftsByThread).toEqual({
      'thread-a': 'Draft A',
      'thread-b': 'Draft B',
    });
  });

  it('handles malformed cookie gracefully', () => {
    mockCookies[DRAFT_COOKIE_NAME] = 'invalid-json';

    // Should not throw
    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.draftsByThread).toEqual({});
  });

  it('handles non-object cookie value gracefully', () => {
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify([1, 2, 3]));

    const { result } = renderHook(() => useMessageDrafts());

    expect(result.current.draftsByThread).toEqual({});
  });

  it('filters non-string values from stored drafts', () => {
    const mixedDrafts = {
      'thread-1': 'Valid string',
      'thread-2': 123,
      'thread-3': null,
    };
    mockCookies[DRAFT_COOKIE_NAME] = encodeURIComponent(JSON.stringify(mixedDrafts));

    const { result } = renderHook(() => useMessageDrafts());

    // Only string values should be kept
    expect(result.current.draftsByThread).toEqual({
      'thread-1': 'Valid string',
    });
  });
});
