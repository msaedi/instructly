import { createConversation } from '../conversations';

const fetchWithSessionRefreshMock = jest.fn();

jest.mock('@/lib/apiBase', () => ({
  withApiBase: (path: string) => `http://localhost${path}`,
  withApiBaseForRequest: (path: string) => `http://localhost${path}`,
}));

jest.mock('@/lib/auth/sessionRefresh', () => ({
  fetchWithSessionRefresh: (...args: Parameters<typeof fetchWithSessionRefreshMock>) =>
    fetchWithSessionRefreshMock(...args),
}));

describe('conversations service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('posts other_user_id when creating or resolving a conversation', async () => {
    fetchWithSessionRefreshMock.mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'conv-1', created: false }),
    });

    await expect(createConversation('user-123', 'Hello there')).resolves.toEqual({
      id: 'conv-1',
      created: false,
    });

    expect(fetchWithSessionRefreshMock).toHaveBeenCalledWith(
      'http://localhost/api/v1/conversations',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          other_user_id: 'user-123',
          initial_message: 'Hello there',
        }),
      })
    );
  });

  it('throws when the create conversation request fails', async () => {
    fetchWithSessionRefreshMock.mockResolvedValue({
      ok: false,
      status: 400,
    });

    await expect(createConversation('user-456')).rejects.toThrow(
      'Failed to create conversation: 400'
    );
  });
});
