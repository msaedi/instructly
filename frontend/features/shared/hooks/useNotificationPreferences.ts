'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/features/shared/hooks/useAuth';
import {
  notificationPreferencesApi,
  type NotificationPreferenceChannels,
  type PreferencesByCategory,
} from '@/features/shared/api/notificationPreferences';

type PreferenceCategory = keyof PreferencesByCategory;
type PreferenceChannel = Extract<keyof NotificationPreferenceChannels, string>;

type UpdatePreferencePayload = {
  category: PreferenceCategory;
  channel: PreferenceChannel;
  enabled: boolean;
};

export function useNotificationPreferences() {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();

  const queryKey = ['notification-preferences'];

  const preferencesQuery = useQuery({
    queryKey,
    queryFn: () => notificationPreferencesApi.getPreferences(),
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });

  const updatePreferenceMutation = useMutation({
    mutationFn: ({ category, channel, enabled }: UpdatePreferencePayload) =>
      notificationPreferencesApi.updatePreference(category, channel, enabled),
    onMutate: async ({ category, channel, enabled }: UpdatePreferencePayload) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<PreferencesByCategory>(queryKey);

      if (previous) {
        queryClient.setQueryData<PreferencesByCategory>(queryKey, {
          ...previous,
          [category]: {
            ...previous[category],
            [channel]: enabled,
          },
        });
      }

      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  return {
    preferences: preferencesQuery.data,
    isLoading: preferencesQuery.isLoading,
    error: preferencesQuery.error,
    updatePreference: (category: PreferenceCategory, channel: PreferenceChannel, enabled: boolean) =>
      updatePreferenceMutation.mutate({ category, channel, enabled }),
    isUpdating: updatePreferenceMutation.isPending,
  };
}
