'use client';

import { useCallback, useState } from 'react';
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

type PendingPreferenceMap = Record<string, true>;

function getPendingPreferenceKey(category: PreferenceCategory, channel: PreferenceChannel) {
  return `${category}:${channel}`;
}

export function useNotificationPreferences() {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [pendingPreferences, setPendingPreferences] = useState<PendingPreferenceMap>({});

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
      const pendingKey = getPendingPreferenceKey(category, channel);

      setPendingPreferences((prev) => ({ ...prev, [pendingKey]: true }));
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

      return { previous, pendingKey };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSettled: (_data, _error, _variables, context) => {
      if (context?.pendingKey) {
        setPendingPreferences((prev) => {
          const next = { ...prev };
          delete next[context.pendingKey];
          return next;
        });
      }

      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const updatePreference = useCallback(
    (category: PreferenceCategory, channel: PreferenceChannel, enabled: boolean) =>
      updatePreferenceMutation.mutate({ category, channel, enabled }),
    [updatePreferenceMutation]
  );

  const isPreferenceUpdating = useCallback(
    (category: PreferenceCategory, channel: PreferenceChannel) =>
      Boolean(pendingPreferences[getPendingPreferenceKey(category, channel)]),
    [pendingPreferences]
  );

  return {
    preferences: preferencesQuery.data,
    isLoading: preferencesQuery.isLoading,
    error: preferencesQuery.error,
    updatePreference,
    isUpdating: Object.keys(pendingPreferences).length > 0,
    isPreferenceUpdating,
  };
}
