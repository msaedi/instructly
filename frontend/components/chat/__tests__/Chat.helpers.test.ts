import {
  canHandleReaction,
  deleteChatBubbleMessage,
  editChatBubbleMessage,
  getEditableChatTarget,
  reactToChatBubbleMessage,
  reloadChatView,
  syncIsAtBottom,
  triggerChatReload,
} from '../Chat.helpers';

describe('Chat helpers', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('does not update bottom state when there is no scroll container', () => {
    const setIsAtBottom = jest.fn();

    expect(syncIsAtBottom(null, setIsAtBottom)).toBe(false);
    expect(setIsAtBottom).not.toHaveBeenCalled();
  });

  it('updates bottom state when scroll metrics are present', () => {
    const setIsAtBottom = jest.fn();

    expect(
      syncIsAtBottom(
        { scrollTop: 900, scrollHeight: 1000, clientHeight: 80 },
        setIsAtBottom,
      ),
    ).toBe(true);
    expect(setIsAtBottom).toHaveBeenCalledWith(true);
  });

  it('returns only editable message targets', () => {
    const messages: Array<{
      id: string;
      sender_id?: string | null;
      is_deleted?: boolean;
      created_at: string;
    }> = [
      { id: 'editable', sender_id: 'u1', is_deleted: false, created_at: new Date().toISOString() },
      { id: 'deleted', sender_id: 'u1', is_deleted: true, created_at: new Date().toISOString() },
    ];

    const canEdit = (message: (typeof messages)[number]) => !message.is_deleted;

    expect(getEditableChatTarget(messages, 'editable', canEdit)).toEqual(messages[0]);
    expect(getEditableChatTarget(messages, 'deleted', canEdit)).toBeNull();
    expect(getEditableChatTarget(messages, 'missing', canEdit)).toBeNull();
  });

  it('only allows reactions when no reaction mutation is already in flight', () => {
    expect(canHandleReaction(null)).toBe(true);
    expect(canHandleReaction('thumbs-up')).toBe(false);
  });

  it('guards edit and delete actions when the target message is missing or immutable', async () => {
    const editMessage = jest.fn();
    const deleteMessage = jest.fn();
    const updateRealtimeMessages = jest.fn();
    const invalidateMessages = jest.fn();
    const messages = [{ id: 'deleted', sender_id: 'u1', is_deleted: true, created_at: new Date().toISOString() }];
    const canEdit = (message: (typeof messages)[number]) => !message.is_deleted;

    await expect(
      editChatBubbleMessage({
        messages,
        messageId: 'missing',
        newContent: 'hello',
        canEditMessage: canEdit,
        editMessage,
      }),
    ).resolves.toBe(false);

    await expect(
      deleteChatBubbleMessage({
        messages,
        messageId: 'deleted',
        canEditMessage: canEdit,
        deleteMessage,
        updateRealtimeMessages,
        invalidateMessages,
      }),
    ).resolves.toBe(false);

    expect(editMessage).not.toHaveBeenCalled();
    expect(deleteMessage).not.toHaveBeenCalled();
    expect(updateRealtimeMessages).not.toHaveBeenCalled();
  });

  it('applies delete side effects and blocks concurrent reactions', async () => {
    const deleteMessage = jest.fn().mockResolvedValue(undefined);
    const updateRealtimeMessages = jest.fn((updater) =>
      updater([{ id: 'msg-1', is_deleted: false, content: 'hello' }]),
    );
    const invalidateMessages = jest.fn().mockResolvedValue(undefined);
    const handleAddReaction = jest.fn().mockResolvedValue(undefined);
    const canEdit = () => true;
    const messages = [{ id: 'msg-1', sender_id: 'u1', is_deleted: false, created_at: new Date().toISOString() }];

    await expect(
      deleteChatBubbleMessage({
        messages,
        messageId: 'msg-1',
        canEditMessage: canEdit,
        deleteMessage,
        updateRealtimeMessages,
        invalidateMessages,
      }),
    ).resolves.toBe(true);

    expect(deleteMessage).toHaveBeenCalledWith({ messageId: 'msg-1' });
    expect(updateRealtimeMessages).toHaveBeenCalled();
    expect(invalidateMessages).toHaveBeenCalled();

    await expect(
      reactToChatBubbleMessage({
        processingReaction: 'msg-1',
        messageId: 'msg-1',
        emoji: '👍',
        handleAddReaction,
      }),
    ).resolves.toBe(false);
    await expect(
      reactToChatBubbleMessage({
        processingReaction: null,
        messageId: 'msg-1',
        emoji: '👍',
        handleAddReaction,
      }),
    ).resolves.toBe(true);
    expect(handleAddReaction).toHaveBeenCalledTimes(1);
  });

  it('reloads the page outside tests and no-ops in test mode', () => {
    const reload = jest.fn();

    reloadChatView(reload, 'production');
    expect(reload).toHaveBeenCalledTimes(1);

    reload.mockClear();
    reloadChatView(reload, 'test');
    expect(reload).not.toHaveBeenCalled();
  });

  it('safely no-ops when triggerChatReload is called in tests', () => {
    expect(() => triggerChatReload()).not.toThrow();
  });
});
