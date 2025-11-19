import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { queryKeys } from '@/lib/react-query/queryClient';
import { useAvailabilityWeekInvalidation } from '../useAvailabilityWeekInvalidation';

describe('useAvailabilityWeekInvalidation', () => {
  const createWrapper = () => {
    const queryClient = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    return { wrapper, queryClient };
  };

  it('invalidates the weekly availability query when invoked', async () => {
    const { wrapper, queryClient } = createWrapper();
    const spy = jest.spyOn(queryClient, 'invalidateQueries').mockResolvedValue(undefined);

    const { result } = renderHook(
      () => useAvailabilityWeekInvalidation('inst-1', '2024-04-01'),
      { wrapper }
    );

    await act(async () => {
      await result.current();
    });

    expect(spy).toHaveBeenCalledWith({
      queryKey: queryKeys.availability.week('inst-1', '2024-04-01'),
    });
  });

  it('no-ops when instructor id or week start is missing', async () => {
    const { wrapper, queryClient } = createWrapper();
    const spy = jest.spyOn(queryClient, 'invalidateQueries').mockResolvedValue(undefined);

    const { result } = renderHook(
      () => useAvailabilityWeekInvalidation(undefined, undefined),
      { wrapper }
    );

    await act(async () => {
      await result.current();
    });

    expect(spy).not.toHaveBeenCalled();
  });
});
