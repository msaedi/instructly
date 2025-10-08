'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { bgcInvite, bgcRecheck, bgcStatus, type BGCStatus } from '@/lib/api/bgc';
import { toast } from 'sonner';
import { IS_NON_PROD } from '@/lib/env';
import { ApiProblemError } from '@/lib/api/fetch';

const POLL_BACKOFF_MS = [15000, 60000, 300000] as const;

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
    label: 'Not started',
    className: 'bg-slate-100 text-slate-700 border border-slate-200',
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

  const resolvedStatus: BGCStatus = status ?? 'failed';
  const meta = STATUS_META[resolvedStatus];

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

interface StatusSnapshot {
  status: BGCStatus | null;
  reportId: string | null;
  completedAt: string | null;
  consentRecent: boolean;
  consentRecentAt: string | null;
  validUntil: string | null;
  expiresInDays: number | null;
  isExpired: boolean;
}

interface BGCStepProps {
  instructorId: string;
  onStatusUpdate?: (status: StatusSnapshot) => void;
  ensureConsent?: () => Promise<boolean>;
}

export function BGCStep({ instructorId, onStatusUpdate, ensureConsent }: BGCStepProps) {
  const [status, setStatus] = React.useState<BGCStatus | null>(null);
  const [reportId, setReportId] = React.useState<string | null>(null);
  const [completedAt, setCompletedAt] = React.useState<string | null>(null);
  const [consentRecent, setConsentRecent] = React.useState(false);
  const [consentRecentAt, setConsentRecentAt] = React.useState<string | null>(null);
  const [validUntil, setValidUntil] = React.useState<string | null>(null);
  const [expiresInDays, setExpiresInDays] = React.useState<number | null>(null);
  const [isExpired, setIsExpired] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [inviteLoading, setInviteLoading] = React.useState(false);
  const [recheckLoading, setRecheckLoading] = React.useState(false);
  const [statusError, setStatusError] = React.useState(false);
  const [isForbidden, setIsForbidden] = React.useState(false);
  const [cooldownActive, setCooldownActive] = React.useState(false);
  const cooldownRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimerRef = React.useRef<number | null>(null);
  const backoffIdxRef = React.useRef(0);
  const statusChipRef = React.useRef<HTMLSpanElement | null>(null);
  const isMountedRef = React.useRef(true);
  const previousStatusRef = React.useRef<BGCStatus | null>(null);
  const statusRef = React.useRef<BGCStatus | null>(null);

  const setStatusSafe = React.useCallback((next: BGCStatus | null) => {
    if (previousStatusRef.current === next) {
      return;
    }
    previousStatusRef.current = next;
    statusRef.current = next;
    setStatus(next);
  }, []);

  React.useEffect(() => {
    statusRef.current = status;
  }, [status]);

  const pushSnapshot = React.useCallback(
    (snapshot: StatusSnapshot) => {
      setStatusSafe(snapshot.status);
      setReportId(snapshot.reportId);
      setCompletedAt(snapshot.completedAt);
      setConsentRecent(snapshot.consentRecent);
      setConsentRecentAt(snapshot.consentRecentAt);
      setValidUntil(snapshot.validUntil);
      setExpiresInDays(snapshot.expiresInDays);
      setIsExpired(snapshot.isExpired);
      onStatusUpdate?.(snapshot);
    },
    [onStatusUpdate, setStatusSafe]
  );

  const snapshotFromResponse = React.useCallback(
    (res: Awaited<ReturnType<typeof bgcStatus>>): StatusSnapshot => ({
      status: res.status ?? 'failed',
      reportId: res.report_id ?? null,
      completedAt: res.completed_at ?? null,
      consentRecent: Boolean(res.consent_recent),
      consentRecentAt: res.consent_recent_at ?? null,
      validUntil: res.valid_until ?? null,
      expiresInDays:
        typeof res.expires_in_days === 'number' ? res.expires_in_days : res.expires_in_days ?? null,
      isExpired: Boolean(res.is_expired),
    }),
    []
  );

  const loadStatus = React.useCallback(async () => {
    if (!isMountedRef.current) return;
    try {
      const res = await bgcStatus(instructorId);
      if (!isMountedRef.current) return;
      pushSnapshot(snapshotFromResponse(res));
      setStatusError(false);
    } catch (error) {
      if (!isMountedRef.current) return;
      const message = error instanceof Error ? error.message : 'Unable to load background check status';
      toast.error(message);
      pushSnapshot({
        status: 'failed',
        reportId: null,
        completedAt: null,
        consentRecent: false,
        consentRecentAt: null,
        validUntil: null,
        expiresInDays: null,
        isExpired: false,
      });
      setStatusError(true);
    }
  }, [instructorId, pushSnapshot, snapshotFromResponse]);

  React.useEffect(() => {
    isMountedRef.current = true;
    let alive = true;
    setLoading(true);
    (async () => {
      try {
        const res = await bgcStatus(instructorId);
        if (!alive || !isMountedRef.current) return;
        pushSnapshot(snapshotFromResponse(res));
        setStatusError(false);
      } catch (error) {
        if (!alive || !isMountedRef.current) return;
        const message = error instanceof Error ? error.message : 'Unable to load background check status';
        toast.error(message);
        pushSnapshot({
          status: 'failed',
          reportId: null,
          completedAt: null,
          consentRecent: false,
          consentRecentAt: null,
          validUntil: null,
          expiresInDays: null,
          isExpired: false,
        });
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
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [instructorId, pushSnapshot, snapshotFromResponse]);

  const scheduleNextPoll = React.useCallback(() => {
    if (backoffIdxRef.current >= POLL_BACKOFF_MS.length) {
      return;
    }

    const delay = POLL_BACKOFF_MS[backoffIdxRef.current];
    pollTimerRef.current = window.setTimeout(async () => {
      pollTimerRef.current = null;
      await loadStatus();
      const currentStatus = statusRef.current;
      if (currentStatus === 'pending' || currentStatus === 'review') {
        backoffIdxRef.current += 1;
        scheduleNextPoll();
      }
    }, delay);
  }, [loadStatus]);

  React.useEffect(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    backoffIdxRef.current = 0;
    if (status === 'pending' || status === 'review') {
      scheduleNextPoll();
    }
    return () => {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [status, scheduleNextPoll]);

  const disabled =
    isForbidden ||
    inviteLoading ||
    loading ||
    cooldownActive ||
    status === 'pending' ||
    status === 'review' ||
    status === 'passed';

  const handleStart = async (afterConsent = false): Promise<void> => {
    setInviteLoading(true);
    setIsForbidden(false);
    let forbiddenError = false;
    let attemptedInvite = false;
    let ensuredAt: string | null = null;
    try {
      if (ensureConsent && !consentRecent) {
        const consentOk = await ensureConsent();
        if (!consentOk) {
          return;
        }
        ensuredAt = new Date().toISOString();
        setConsentRecent(true);
        setConsentRecentAt(ensuredAt);
      }
      const res = await bgcInvite(instructorId);
      attemptedInvite = true;
      if (res.already_in_progress) {
        toast.success('Background check already in progress');
      } else {
        toast.success('Background check started');
      }
      pushSnapshot({
        status: res.status,
        reportId: res.report_id ?? null,
        completedAt,
        consentRecent: true,
        consentRecentAt: ensuredAt ?? consentRecentAt,
        validUntil: null,
        expiresInDays: null,
        isExpired: false,
      });
      setStatusError(false);
      await loadStatus();
      statusChipRef.current?.focus();
    } catch (error) {
      let description = 'Please try again in a moment.';
      if (error instanceof ApiProblemError) {
        const detail = error.problem?.detail;
        const detailObject =
          typeof detail === 'object' && detail !== null ? (detail as Record<string, unknown>) : null;
        const detailMessage =
          typeof detail === 'string' && detail.trim().length > 0
            ? detail
            : detailObject && typeof detailObject['message'] === 'string'
              ? (detailObject['message'] as string)
              : undefined;
        const code = detailObject && typeof detailObject['code'] === 'string' ? (detailObject['code'] as string) : undefined;
        description = detailMessage ?? description;
        if (error.response.status === 403) {
          setIsForbidden(true);
          toast.info('Only the owner can start a background check.', {
            description,
          });
          forbiddenError = true;
        } else if (code === 'bgc_consent_required' && ensureConsent && !afterConsent) {
          const consentOk = await ensureConsent();
          if (consentOk) {
            ensuredAt = new Date().toISOString();
            setConsentRecent(true);
            setConsentRecentAt(ensuredAt);
            await handleStart(true);
            return;
          }
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

  const handleRecheck = async (afterConsent = false): Promise<void> => {
    setRecheckLoading(true);
    let ensuredAt: string | null = null;
    try {
      if (ensureConsent && !consentRecent) {
        const consentOk = await ensureConsent();
        if (!consentOk) {
          return;
        }
        ensuredAt = new Date().toISOString();
        setConsentRecent(true);
        setConsentRecentAt(ensuredAt);
      }

      const res = await bgcRecheck(instructorId);
      if (res.already_in_progress) {
        toast.success('Background check already in progress');
      } else {
        toast.success('Background check re-check started');
      }
      pushSnapshot({
        status: res.status,
        reportId: res.report_id ?? reportId,
        completedAt,
        consentRecent: true,
        consentRecentAt: ensuredAt ?? consentRecentAt,
        validUntil: null,
        expiresInDays: null,
        isExpired: false,
      });
      setStatusError(false);
      await loadStatus();
      statusChipRef.current?.focus();
    } catch (error) {
      if (error instanceof ApiProblemError) {
        const statusCode = error.response.status;
        const code = error.problem.code;
        const detailMessage = error.problem.detail;
        if (code === 'bgc_consent_required' && ensureConsent && !afterConsent) {
          const consentOk = await ensureConsent();
          if (consentOk) {
            ensuredAt = new Date().toISOString();
            setConsentRecent(true);
            setConsentRecentAt(ensuredAt);
            await handleRecheck(true);
            return;
          }
        } else if (statusCode === 429) {
          toast.info('You can try again later.');
        } else {
          const description = detailMessage && detailMessage.length > 0 ? detailMessage : 'Please try again in a moment.';
          toast.error('Unable to re-check background', { description });
        }
      } else {
        toast.error('Unable to re-check background', {
          description: 'Please try again. If the problem persists, contact support.',
        });
      }
    } finally {
      setRecheckLoading(false);
    }
  };

  const validUntilLabel = React.useMemo(() => {
    if (!validUntil) return null;
    try {
      return new Date(validUntil).toLocaleDateString();
    } catch {
      return null;
    }
  }, [validUntil]);

  const shouldShowRecheck =
    isExpired || (typeof expiresInDays === 'number' && Number.isFinite(expiresInDays) && expiresInDays <= 30);
  const recheckDisabled =
    recheckLoading ||
    inviteLoading ||
    loading ||
    status === 'pending' ||
    status === 'review';

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
      <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
        <span>Valid until: {validUntilLabel ?? '—'}</span>
        {shouldShowRecheck ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleRecheck()}
            disabled={recheckDisabled}
            aria-disabled={recheckDisabled}
          >
            {recheckLoading ? 'Re-checking…' : 'Re-check'}
          </Button>
        ) : null}
      </div>
      {statusError ? (
        <p className="text-sm text-muted-foreground" role="alert">
          Status unavailable. You can still start a background check.
        </p>
      ) : null}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-4">
        <Button
          onClick={() => void handleStart()}
          disabled={disabled}
          aria-disabled={disabled}
          className="w-full sm:w-auto rounded-lg sm:rounded-md text-base sm:text-sm h-auto sm:h-10 px-4 py-2 bg-[#7E22CE] hover:bg-[#7E22CE] text-white shadow-sm"
        >
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
