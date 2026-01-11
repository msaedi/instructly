import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { phoneApi, PhoneStatusResponse } from '@/features/shared/api/phone';

export function usePhoneVerification() {
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ['phone-status'],
    queryFn: phoneApi.getPhoneStatus,
    staleTime: 5 * 60 * 1000,
  });

  const updatePhone = useMutation({
    mutationFn: (phoneNumber: string) => phoneApi.updatePhoneNumber(phoneNumber),
    onSuccess: (updated) => {
      queryClient.setQueryData<PhoneStatusResponse>(['phone-status'], updated);
    },
  });

  const sendVerification = useMutation({
    mutationFn: () => phoneApi.sendVerification(),
  });

  const confirmVerification = useMutation({
    mutationFn: (code: string) => phoneApi.confirmVerification(code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['phone-status'] });
    },
  });

  return {
    phoneNumber: data?.phone_number ?? '',
    isVerified: data?.verified ?? false,
    isLoading,
    isError,
    updatePhone,
    sendVerification,
    confirmVerification,
  };
}
