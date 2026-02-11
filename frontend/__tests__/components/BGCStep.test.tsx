process.env.NEXT_PUBLIC_APP_ENV = 'preview';

import * as React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BGCStep } from '@/components/instructor/BGCStep';
import { bgcInvite, bgcRecheck, bgcStatus } from '@/lib/api/bgc';
import type { BGCInviteResponse, BGCStatusResponse } from '@/lib/api/bgc';
import { ApiProblemError } from '@/lib/api/fetch';
import { normalizeProblem } from '@/lib/errors/problem';
import { toast } from 'sonner';

jest.mock('@/lib/api/bgc');

jest.mock('sonner', () => {
  const fn = Object.assign(jest.fn(), {
    error: jest.fn(),
    success: jest.fn(),
    info: jest.fn(),
  });
  return { toast: fn };
});

const originalConsoleWarn = console.warn.bind(console);
const makeStatus = (overrides: Partial<BGCStatusResponse>): BGCStatusResponse => ({
  status: 'pending',
  env: 'sandbox',
  consent_recent: false,
  is_expired: false,
  ...overrides,
});
const makeInvite = (overrides: Partial<BGCInviteResponse>): BGCInviteResponse => ({
  status: 'pending',
  ok: true,
  already_in_progress: false,
  ...overrides,
});

beforeAll(() => {
  jest.spyOn(console, 'warn').mockImplementation((...args: unknown[]) => {
    const [message] = args;
    if (
      typeof message === 'string' &&
      message.includes('A function to advance timers was called but the timers APIs are not replaced with fake timers')
    ) {
      return;
    }
    originalConsoleWarn(...args);
  });
});

afterAll(() => {
  (console.warn as jest.Mock).mockRestore();
});

describe('BGCStep', () => {
  const mockedBGCStatus = bgcStatus as jest.MockedFunction<typeof bgcStatus>;
  const mockedBGCInvite = bgcInvite as jest.MockedFunction<typeof bgcInvite>;
  const mockedBGCRecheck = bgcRecheck as jest.MockedFunction<typeof bgcRecheck>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockedBGCStatus.mockReset();
    mockedBGCInvite.mockReset();
    mockedBGCRecheck.mockReset();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('shows pending status chip, hides CTA, and shows inline pending banner', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'pending' }));

    render(<BGCStep instructorId="instructor-123" />);

    expect(await screen.findByText(/Verification pending/)).toBeInTheDocument();
    expect(await screen.findByText('Valid until: —')).toBeInTheDocument();

    // Button is hidden for pending status (Issue #19)
    expect(screen.queryByRole('button', { name: /start background check/i })).not.toBeInTheDocument();

    // Timing message still shown
    expect(screen.getByText(/full results typically 1–3 business days/)).toBeInTheDocument();

    // Amber inline banner shown
    expect(screen.getByText(/Please continue via the email we sent you/)).toBeInTheDocument();
  });

  it('displays ETA when provided for pending status', async () => {
    const etaIso = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString();
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'pending', eta: etaIso }));

    render(<BGCStep instructorId="instructor-eta" />);

    const expectedEta = new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(new Date(etaIso));
    const etaLine = await screen.findByText(/Estimated completion/i);
    expect(etaLine).toHaveTextContent(expectedEta);
  });

  it('invites background check with debounce and confirmation modal', async () => {
    const timeoutSpy = jest.spyOn(global, 'setTimeout');
    mockedBGCStatus
      .mockResolvedValueOnce(makeStatus({ status: 'failed' }))
      .mockResolvedValueOnce(makeStatus({ status: 'pending', report_id: 'RPT-1' }));

    mockedBGCInvite.mockResolvedValue(makeInvite({ status: 'pending', report_id: 'RPT-1' }));

    render(<BGCStep instructorId="instructor-456" />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(screen.getByText(/Not started/)).toBeInTheDocument());
    await waitFor(() => expect(button).not.toBeDisabled());

    await userEvent.click(button);

    await waitFor(() => {
      expect(mockedBGCInvite).toHaveBeenCalledWith('instructor-456');
    });
    expect(screen.getAllByText('Check your email to continue').length).toBeGreaterThan(0);
    const debounceCall = timeoutSpy.mock.calls.find(([, delay]) => delay === 1000);
    expect(debounceCall).toBeTruthy();
    timeoutSpy.mockRestore();
  });

  it('waits for consent before starting invite', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'failed' }));
    const ensureConsent = jest.fn().mockResolvedValueOnce(false);

    render(<BGCStep instructorId="instructor-consent" ensureConsent={ensureConsent} />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());

    await userEvent.click(button);

    await waitFor(() => {
      expect(ensureConsent).toHaveBeenCalledTimes(1);
    });
    expect(mockedBGCInvite).not.toHaveBeenCalled();
  });

  it('shows neutral toast when already in progress', async () => {
    mockedBGCStatus
      .mockResolvedValueOnce(makeStatus({ status: 'failed' }))
      .mockResolvedValueOnce(makeStatus({ status: 'failed' }));

    mockedBGCInvite.mockResolvedValue(
      makeInvite({ status: 'failed', report_id: 'RPT-2', already_in_progress: true })
    );

    render(<BGCStep instructorId="instructor-789" />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() => {
      expect(mockedBGCInvite).toHaveBeenCalledWith('instructor-789');
    });
    expect(toast.success).toHaveBeenCalledWith('Background check already in progress');
  });

  it('displays canceled status messaging and keeps CTA enabled', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'canceled' }));

    render(<BGCStep instructorId="instructor-canceled" />);

    expect(await screen.findByText(/Canceled/)).toBeInTheDocument();
    expect(
      await screen.findByText(/Background check was canceled in Checkr/i),
    ).toBeInTheDocument();
    const button = await screen.findByRole('button', { name: /start background check/i });
    expect(button).not.toBeDisabled();
  });

  it('disables CTA and shows message when forbidden', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'failed' }));
    const response = { status: 403 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Forbidden',
      status: 403,
      detail: 'Only owner can trigger.',
    };
    mockedBGCInvite.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-999" />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() => {
      expect(toast.info).toHaveBeenCalledWith('Only the owner can start a background check.', expect.any(Object));
    });
    expect(button).toBeDisabled();
    expect(screen.getByText('Only the owner can start a background check.')).toBeInTheDocument();
  });

  it('shows auth failure message when Checkr rejects credentials during invite', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'failed' }));
    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Checkr authentication failed',
      status: 400,
      detail: 'Checkr API key is invalid or not authorized for the configured environment.',
      code: 'checkr_auth_error',
    };
    mockedBGCInvite.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-auth-error" />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Background check provider authentication failed',
        expect.objectContaining({ description: expect.stringContaining('Checkr API key configuration') })
      )
    );
  });

  it('shows package misconfiguration message when Checkr rejects invite package', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'failed' }));
    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Checkr package misconfigured',
      status: 400,
      detail: 'The configured Checkr package slug does not exist.',
      code: 'checkr_package_not_found',
    };
    mockedBGCInvite.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-package-error" />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Background check configuration error: Checkr package slug is invalid.',
        expect.objectContaining({ description: expect.stringContaining('Checkr package configuration') })
      )
    );
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it('shows invalid ZIP message when backend reports invalid work location', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'failed' }));
    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Invalid work location',
      status: 400,
      detail: 'ZIP missing',
      code: 'invalid_work_location',
    };
    mockedBGCInvite.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-invalid-zip" />);
    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Your primary teaching ZIP code is missing or invalid.',
        expect.objectContaining({ description: expect.stringContaining('update your ZIP code') })
      )
    );
  });

  it('shows provider work location error when Checkr rejects work_locations', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'failed' }));
    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Checkr work location error',
      status: 400,
      detail: 'work_locations invalid',
      code: 'checkr_work_location_error',
    };
    mockedBGCInvite.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-work-location-error" />);
    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Background check configuration error: work location rejected.',
        expect.objectContaining({ description: expect.stringContaining('contact support') })
      )
    );
  });

  it('polls pending status with backoff 15s→60s→300s then clears when passed', async () => {
    jest.useFakeTimers();
    mockedBGCStatus
      .mockResolvedValueOnce(makeStatus({ status: 'pending' }))
      .mockResolvedValueOnce(makeStatus({ status: 'pending' }))
      .mockResolvedValueOnce(makeStatus({ status: 'pending' }))
      .mockResolvedValueOnce(makeStatus({ status: 'passed', completed_at: '2025-01-01T00:00:00Z' }));

    render(<BGCStep instructorId="instructor-poll" />);

    await waitFor(() => expect(screen.getByText(/Verification pending/)).toBeInTheDocument());
    expect(mockedBGCStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      jest.advanceTimersByTime(15000);
    });
    await waitFor(() => expect(mockedBGCStatus).toHaveBeenCalledTimes(2));

    await act(async () => {
      jest.advanceTimersByTime(60000);
    });
    await waitFor(() => expect(mockedBGCStatus).toHaveBeenCalledTimes(3));

    await act(async () => {
      jest.advanceTimersByTime(300000);
    });
    await waitFor(() => expect(mockedBGCStatus).toHaveBeenCalledTimes(4));
    await waitFor(() => expect(screen.getByText(/Verified/)).toBeInTheDocument());

    await act(async () => {
      jest.advanceTimersByTime(600000);
    });
    expect(mockedBGCStatus).toHaveBeenCalledTimes(4);
  });

  it('polls review status with identical backoff and stops after completion', async () => {
    jest.useFakeTimers();
    mockedBGCStatus
      .mockResolvedValueOnce(makeStatus({ status: 'review' }))
      .mockResolvedValueOnce(makeStatus({ status: 'review' }))
      .mockResolvedValueOnce(makeStatus({ status: 'review' }))
      .mockResolvedValueOnce(makeStatus({ status: 'passed', completed_at: '2025-02-02T00:00:00Z' }));

    render(<BGCStep instructorId="instructor-review" />);

    await waitFor(() => expect(screen.getByText(/Under review/)).toBeInTheDocument());
    expect(mockedBGCStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      jest.advanceTimersByTime(15000);
    });
    await waitFor(() => expect(mockedBGCStatus).toHaveBeenCalledTimes(2));

    await act(async () => {
      jest.advanceTimersByTime(60000);
    });
    await waitFor(() => expect(mockedBGCStatus).toHaveBeenCalledTimes(3));

    await act(async () => {
      jest.advanceTimersByTime(300000);
    });
    await waitFor(() => expect(mockedBGCStatus).toHaveBeenCalledTimes(4));
    await waitFor(() => expect(screen.getByText(/Verified/)).toBeInTheDocument());

    await act(async () => {
      jest.advanceTimersByTime(600000);
    });
    expect(mockedBGCStatus).toHaveBeenCalledTimes(4);
  });

  it('allows re-check when validity is expiring', async () => {
    const soon = new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString();
    mockedBGCStatus
      .mockResolvedValueOnce(
        makeStatus({
          status: 'passed',
          consent_recent: true,
          valid_until: soon,
          expires_in_days: 5,
          is_expired: false,
        })
      )
      .mockResolvedValueOnce(makeStatus({ status: 'pending', is_expired: false }));

    mockedBGCRecheck.mockResolvedValue(makeInvite({ status: 'pending', report_id: 'RPT-R' }));

    render(<BGCStep instructorId="instructor-recheck" />);

    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await userEvent.click(recheckButton);

    await waitFor(() => expect(mockedBGCRecheck).toHaveBeenCalledWith('instructor-recheck'));
    expect(toast.success).toHaveBeenCalledWith('Background check re-check started');
  });

  it('requests consent before re-checking when needed', async () => {
    mockedBGCStatus
      .mockResolvedValueOnce(
        makeStatus({
          status: 'passed',
          consent_recent: false,
          valid_until: null,
          expires_in_days: 0,
          is_expired: true,
        })
      )
      .mockResolvedValueOnce(makeStatus({ status: 'pending' }));

    const ensureConsent = jest.fn().mockResolvedValue(true);
    mockedBGCRecheck.mockResolvedValue(makeInvite({ status: 'pending', report_id: 'RPT-R2' }));

    render(<BGCStep instructorId="instructor-recheck-consent" ensureConsent={ensureConsent} />);

    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await userEvent.click(recheckButton);

    await waitFor(() => expect(ensureConsent).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockedBGCRecheck).toHaveBeenCalledWith('instructor-recheck-consent'));
  });

  it('shows retry info when re-check is rate limited', async () => {
    mockedBGCStatus.mockResolvedValueOnce(
      makeStatus({
        status: 'passed',
        consent_recent: true,
        valid_until: null,
        expires_in_days: 0,
        is_expired: true,
      })
    );

    const response = { status: 429 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Rate limited',
      status: 429,
      detail: 'Rate limited',
    };
    mockedBGCRecheck.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-recheck-limit" />);

    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await userEvent.click(recheckButton);

    await waitFor(() => expect(toast.info).toHaveBeenCalledWith('You can try again later.'));
  });

  it('shows auth failure message when Checkr rejects re-check credentials', async () => {
    mockedBGCStatus.mockResolvedValueOnce(
      makeStatus({
        status: 'passed',
        consent_recent: true,
        valid_until: null,
        expires_in_days: 0,
        is_expired: true,
      })
    );

    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Checkr authentication failed',
      status: 400,
      detail: 'Checkr API key is invalid or not authorized for the configured environment.',
      code: 'checkr_auth_error',
    };
    mockedBGCRecheck.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-recheck-auth-error" />);
    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await userEvent.click(recheckButton);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Background check provider authentication failed',
        expect.objectContaining({ description: expect.stringContaining('Checkr API key configuration') })
      )
    );
  });

  it('shows package misconfiguration message when Checkr rejects re-check package', async () => {
    mockedBGCStatus.mockResolvedValueOnce(
      makeStatus({
        status: 'passed',
        consent_recent: true,
        valid_until: null,
        expires_in_days: 0,
        is_expired: true,
      })
    );

    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Checkr package misconfigured',
      status: 400,
      detail: 'The configured Checkr package slug does not exist.',
      code: 'checkr_package_not_found',
    };
    mockedBGCRecheck.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-recheck-package-error" />);
    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await userEvent.click(recheckButton);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Background check configuration error: Checkr package slug is invalid.',
        expect.objectContaining({ description: expect.stringContaining('Checkr package configuration') })
      )
    );
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it('shows invalid ZIP message when backend reports invalid work location for re-check', async () => {
    mockedBGCStatus.mockResolvedValueOnce(
      makeStatus({
        status: 'passed',
        consent_recent: true,
        valid_until: null,
        expires_in_days: 0,
        is_expired: true,
      })
    );

    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Invalid work location',
      status: 400,
      detail: 'ZIP missing',
      code: 'invalid_work_location',
    };
    mockedBGCRecheck.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-recheck-invalid-zip" />);
    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await userEvent.click(recheckButton);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Your primary teaching ZIP code is missing or invalid.',
        expect.objectContaining({ description: expect.stringContaining('update your ZIP code') })
      )
    );
  });

  it('shows provider work location error when Checkr rejects re-check work_locations', async () => {
    mockedBGCStatus.mockResolvedValueOnce(
      makeStatus({
        status: 'passed',
        consent_recent: true,
        valid_until: null,
        expires_in_days: 0,
        is_expired: true,
      })
    );

    const response = { status: 400 } as Response;
    const problem = {
      type: 'about:blank',
      title: 'Checkr work location error',
      status: 400,
      detail: 'work_locations invalid',
      code: 'checkr_work_location_error',
    };
    mockedBGCRecheck.mockRejectedValueOnce(new ApiProblemError(problem, response));

    render(<BGCStep instructorId="instructor-recheck-work-location-error" />);
    const recheckButton = await screen.findByRole('button', { name: /^Re-check$/i });
    await userEvent.click(recheckButton);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Background check configuration error: work location rejected.',
        expect.objectContaining({ description: expect.stringContaining('contact support') })
      )
    );
  });

  it('shows rate limited toast when invite is rate limited', async () => {
    mockedBGCStatus.mockResolvedValueOnce(makeStatus({ status: 'failed' }));
    const response = { status: 429 } as Response;
    const structuredDetail = {
      status: 429,
      code: 'bgc_invite_rate_limited',
      title: 'Background check recently requested',
      message: 'You recently started a background check. Please wait up to 24 hours before trying again.',
    };
    const normalized = normalizeProblem(structuredDetail, 429);
    mockedBGCInvite.mockRejectedValueOnce(new ApiProblemError(normalized, response));

    render(<BGCStep instructorId="instructor-rate-limit" />);
    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        'You recently requested a background check. Please wait up to 24 hours before starting another one.'
      )
    );
    expect(toast.error).not.toHaveBeenCalled();
  });
});
