'use client';

import { useCallback, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { isPaused } from '@/lib/accountStatus';
import { queryKeys } from '@/src/api/queryKeys';
import PausedAccountBanner from '@/components/security/PausedAccountBanner';
import ResumeAccountModal from '@/components/security/ResumeAccountModal';
import {
  accountStatusQueryKey,
  useAccountStatus,
  useReactivateAccount,
} from '@/hooks/queries/useAccountStatus';

function isSettingsPath(pathname: string | null): boolean {
  return pathname === '/instructor/settings' || Boolean(pathname?.startsWith('/instructor/settings/'));
}

export default function InstructorPausedAccountBanner() {
  const pathname = usePathname();
  const hideOnSettings = isSettingsPath(pathname);
  const [showResumeModal, setShowResumeModal] = useState(false);
  const queryClient = useQueryClient();
  const { data: accountStatusData } = useAccountStatus(!hideOnSettings);
  const reactivateAccount = useReactivateAccount();
  const isAccountPaused = isPaused(accountStatusData?.account_status);

  const refreshAccountLifecycleQueries = useCallback(async () => {
    await Promise.allSettled([
      queryClient.invalidateQueries({ queryKey: accountStatusQueryKey }),
      queryClient.invalidateQueries({ queryKey: queryKeys.auth.me }),
      queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me }),
    ]);
  }, [queryClient]);

  const handleResumeConfirm = useCallback(async () => {
    try {
      await reactivateAccount.mutateAsync();
      await refreshAccountLifecycleQueries();
      setShowResumeModal(false);
      toast.success('Account resumed. Check your email for confirmation.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to resume account.');
    }
  }, [reactivateAccount, refreshAccountLifecycleQueries]);

  if (hideOnSettings || !isAccountPaused) {
    return null;
  }

  return (
    <div className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
      <PausedAccountBanner onResume={() => setShowResumeModal(true)} />
      {showResumeModal && (
        <ResumeAccountModal
          onClose={() => setShowResumeModal(false)}
          onConfirm={() => void handleResumeConfirm()}
          isSubmitting={reactivateAccount.isPending}
        />
      )}
    </div>
  );
}
