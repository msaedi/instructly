import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useCreateConversation } from '../useCreateConversation';
import { createConversation, conversationQueryKeys } from '@/src/api/services/conversations';
import { useRouter } from 'next/navigation';
import { logger } from '@/lib/logger';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('@/src/api/services/conversations', () => ({
  createConversation: jest.fn(),
  conversationQueryKeys: { all: ['conversations'] },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    error: jest.fn(),
  },
}));

const createConversationMock = createConversation as jest.Mock;
const useRouterMock = useRouter as jest.Mock;
const loggerErrorMock = logger.error as jest.Mock;

describe('useCreateConversation', () => {
  const push = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    useRouterMock.mockReturnValue({ push });
  });

  const createWrapper = () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = jest.spyOn(queryClient, 'invalidateQueries');
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    Wrapper.displayName = 'QueryClientWrapper';
    return { Wrapper, invalidateSpy };
  };

  it('creates a conversation and navigates by default', async () => {
    createConversationMock.mockResolvedValue({ id: 'conv-1', created: true });
    const { Wrapper, invalidateSpy } = createWrapper();

    const { result } = renderHook(() => useCreateConversation(), { wrapper: Wrapper });

    await act(async () => {
      const response = await result.current.createConversation('instr-1');
      expect(response).toEqual({ id: 'conv-1', created: true });
    });

    expect(push).toHaveBeenCalledWith('/instructor/messages?conversation=conv-1');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: conversationQueryKeys.all });
  });

  it('skips navigation when navigateToMessages is false', async () => {
    createConversationMock.mockResolvedValue({ id: 'conv-2', created: false });
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useCreateConversation(), { wrapper: Wrapper });

    await act(async () => {
      await result.current.createConversation('instr-2', { navigateToMessages: false });
    });

    expect(push).not.toHaveBeenCalled();
  });

  it('logs and rethrows when creation fails', async () => {
    const error = new Error('Failed');
    createConversationMock.mockRejectedValue(error);
    const { Wrapper } = createWrapper();

    const { result } = renderHook(() => useCreateConversation(), { wrapper: Wrapper });

    await act(async () => {
      await expect(result.current.createConversation('instr-3')).rejects.toThrow('Failed');
    });

    expect(loggerErrorMock).toHaveBeenCalledWith('Failed to create conversation', error);
  });
});
