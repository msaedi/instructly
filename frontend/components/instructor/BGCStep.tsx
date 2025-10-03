'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { bgcInvite, bgcStatus, type BGCStatus } from '@/lib/api/bgc';
import { toast } from 'sonner';
import { IS_NON_PROD } from '@/lib/env';
import { ApiProblemError } from '@/lib/api/fetch';

const STATUS_META: Record<BGCStatus, { label: string; className: string }> = {
  passed: {
    label: 'Verified',
    className: 'bg-emerald-100 text-emerald-800 border border-emerald-200',
  },
  pending: {
    label: 'Verification pending',
    className: 'bg-amber-100 text-amber-800 border border-amber-200',
  },
  review: {
    label: 'Under review',
    className: 'bg-orange-100 text-orange-800 border border-orange-200',
  },
  failed: {
    label: 'Not approved',
    className: 'bg-red-100 text-red-700 border border-red-200',
  },
};

interface StatusChipProps {
  status: BGCStatus | null;
  loading: boolean;
}

const StatusChip = React.forwardRef<HTMLSpanElement, StatusChipProps>(({ status, loading }, ref) => {
  if (loading) {
    return (
      <span className="inline-flex focus:outline-none" role="status" tabIndex={-1} ref={ref}>
        <Badge className="border border-gray-200 bg-gray-100 text-gray-600 animate-pulse">
          Checking status…
        </Badge>
      </span>
    );
  }

  if (!status) {
    return (
      <span className="inline-flex focus:outline-none" role="status" tabIndex={-1} ref={ref}>
        <Badge className="border border-gray-200 bg-gray-100 text-gray-600">
          Status unavailable
        </Badge>
      </span>
    );
  }

  const meta = STATUS_META[status];

  return (
    <span className="inline-flex focus:outline-none" role="status" tabIndex={-1} ref={ref}>
      <Badge className={cn('font-medium', meta.className)}>
        {meta.label}
        {IS_NON_PROD && ' (Test)'}
      </Badge>
    </span>
  );
});

StatusChip.displayName = 'StatusChip';

interface BGCStepProps {
  instructorId: string;
  onStatusUpdate?: (status: {
    status: BGCStatus | null;
    reportId: string | null;
    completedAt: string | null;
  }) => void;
  ensureConsent?: () => Promise<boolean>;
}

export function BGCStep({ instructorId, onStatusUpdate, ensureConsent }: BGCStepProps) {
  const [status, setStatus] = React.useState<BGCStatus | null>(null);
  const [reportId, setReportId] = React.useState<string | null>(null);
  const [completedAt, setCompletedAt] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [inviteLoading, setInviteLoading] = React.useState(false);
  const [statusError, setStatusError] = React.useState(false);
  const [isForbidden, setIsForbidden] = React.useState(false);
  const [cooldownActive, setCooldownActive] = React.useState(false);
  const cooldownRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusChipRef = React.useRef<HTMLSpanElement | null>(null);
  const isMountedRef = React.useRef(true);
  const previousStatusRef = React.useRef<BGCStatus | null>(null);

  const setStatusSafe = React.useCallback((next: BGCStatus | null) => {
    if (previousStatusRef.current === next) {
      return;
    }
    previousStatusRef.current = next;
    setStatus(next);
  }, []);

  const pushSnapshot = React.useCallback(
    (snapshot: { status: BGCStatus | null; reportId: string | null; completedAt: string | null }) => {
      setStatusSafe(snapshot.status);
      setReportId(snapshot.reportId);
      setCompletedAt(snapshot.completedAt);
      onStatusUpdate?.(snapshot);
    },
    [onStatusUpdate, setStatusSafe]
  );

  const loadStatus = React.useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const res = await bgcStatus(instructorId);
      if (!isMountedRef.current) return;
      pushSnapshot({
        status: res.status,
        reportId: res.report_id ?? null,
        completedAt: res.completed_at ?? null,
      });
      setStatusError(false);
    } catch (error) {
      if (!isMountedRef.current) return;
      const message = error instanceof Error ? error.message : 'Unable to load background check status';
      toast.error(message);
      pushSnapshot({ status: 'failed', reportId: null, completedAt: null });
      setStatusError(true);
    }
  }, [instructorId, pushSnapshot]);

  React.useEffect(() => {
    isMountedRef.current = true;
    let alive = true;
    setLoading(true);
    (async () => {
      try {
        const res = await bgcStatus(instructorId);
        if (!alive || !isMountedRef.current) return;
        pushSnapshot({
          status: res.status,
          reportId: res.report_id ?? null,
          completedAt: res.completed_at ?? null,
        });
        setStatusError(false);
      } catch (error) {
        if (!alive || !isMountedRef.current) return;
        const message = error instanceof Error ? error.message : 'Unable to load background check status';
        toast.error(message);
        pushSnapshot({ status: 'failed', reportId: null, completedAt: null });
        setStatusError(true);
      } finally {
        if (alive && isMountedRef.current) {
          setLoading(false);
        }
      }
    })();
    return () => {
      alive = false;
      isMountedRef.current = false;
      if (cooldownRef.current) {
        clearTimeout(cooldownRef.current);
      }
    };
  }, [instructorId, pushSnapshot]);

  React.useEffect(() => {
    if (status !== 'pending' && status !== 'review') {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void loadStatus();
    }, 15000);
    return () => window.clearInterval(intervalId);
  }, [status, loadStatus]);

  const disabled =
    isForbidden ||
    inviteLoading ||
    loading ||
    cooldownActive ||
    status === 'pending' ||
    status === 'review' ||
    status === 'passed';

  const handleStart = async () => {
    setInviteLoading(true);
    setIsForbidden(false);
    let forbiddenError = false;
    let attemptedInvite = false;
    try {
      if (ensureConsent) {
        const consentOk = await ensureConsent();
        if (!consentOk) {
          return;
        }
      }
      const res = await bgcInvite(instructorId);
      attemptedInvite = true;
      if (res.already_in_progress) {
        toast.success('Background check already in progress');
      } else {
        toast.success('Background check started');
      }
      pushSnapshot({ status: res.status, reportId: res.report_id ?? null, completedAt });
      setStatusError(false);
      await loadStatus();
      statusChipRef.current?.focus();
    } catch (error) {
      let description = 'Please try again in a moment.';
      if (error instanceof ApiProblemError) {
        const detail = error.problem?.detail;
        description = typeof detail === 'string' && detail.trim().length > 0 ? detail : description;
        if (error.response.status === 403) {
          setIsForbidden(true);
          toast.info('Only the owner can start a background check.', {
            description,
          });
          forbiddenError = true;
        } else {
          toast.error('Unable to start background check', {
            description: 'Please try again. If the problem persists, contact support.',
          });
        }
      } else {
        toast.error('Unable to start background check', {
          description: 'Please try again. If the problem persists, contact support.',
        });
      }
    } finally {
      setInviteLoading(false);
      if (attemptedInvite && !forbiddenError) {
        setCooldownActive(true);
        if (cooldownRef.current) clearTimeout(cooldownRef.current);
        cooldownRef.current = setTimeout(() => {
          setCooldownActive(false);
        }, 1000);
      }
    }
  };

  return (
    <div className="space-y-4" data-testid="bgc-step">
      <div className="flex flex-wrap items-center gap-3" aria-live="polite">
        <StatusChip status={status} loading={loading} ref={statusChipRef} />
        {reportId ? (
          <span className="text-xs text-muted-foreground break-all">Report ID: {reportId}</span>
        ) : null}
        {completedAt ? (
          <span className="text-xs text-muted-foreground">Completed {new Date(completedAt).toLocaleDateString()}</span>
        ) : null}
      </div>
      {statusError ? (
        <p className="text-sm text-muted-foreground" role="alert">
          Status unavailable. You can still start a background check.
        </p>
      ) : null}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-4">
        <Button onClick={handleStart} disabled={disabled} aria-disabled={disabled}>
          {inviteLoading ? 'Starting…' : 'Start background check'}
        </Button>
        <p className="text-sm text-muted-foreground max-w-xl">
          Most approvals are same-day; <span className="font-medium">full results typically 1–3 business days</span>.
          {' '}Your info is collected securely by our screening partner.
        </p>
      </div>
      {isForbidden ? (
        <p className="text-sm text-muted-foreground" role="alert">
          Only the owner can start a background check.
        </p>
      ) : null}
    </div>
  );
}

export default BGCStep;
