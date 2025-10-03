process.env.NEXT_PUBLIC_APP_ENV = 'preview';

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BGCStep } from '@/components/instructor/BGCStep';
import { bgcInvite, bgcStatus } from '@/lib/api/bgc';
import { ApiProblemError } from '@/lib/api/fetch';
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

describe('BGCStep', () => {
  const mockedBGCStatus = bgcStatus as jest.MockedFunction<typeof bgcStatus>;
  const mockedBGCInvite = bgcInvite as jest.MockedFunction<typeof bgcInvite>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockedBGCStatus.mockReset();
    mockedBGCInvite.mockReset();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('shows pending status chip and disables CTA', async () => {
    mockedBGCStatus.mockResolvedValueOnce({
      status: 'pending',
      env: 'sandbox',
    });

    render(<BGCStep instructorId="instructor-123" />);

    expect(await screen.findByText(/Verification pending/)).toBeInTheDocument();

    const button = screen.getByRole('button', { name: /start background check/i });
    expect(button).toBeDisabled();
  });

  it('invites background check with debounce and success toast', async () => {
    const timeoutSpy = jest.spyOn(global, 'setTimeout');
    mockedBGCStatus
      .mockResolvedValueOnce({ status: 'failed', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'failed', env: 'sandbox', report_id: 'RPT-1' });

    mockedBGCInvite.mockResolvedValue({
      ok: true,
      status: 'failed',
      report_id: 'RPT-1',
    });

    render(<BGCStep instructorId="instructor-456" />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(screen.getByText(/Not started/)).toBeInTheDocument());
    await waitFor(() => expect(button).not.toBeDisabled());

    await userEvent.click(button);

    await waitFor(() => {
      expect(mockedBGCInvite).toHaveBeenCalledWith('instructor-456');
    });
    expect(toast.success).toHaveBeenCalledWith('Background check started');
    expect(button).toBeDisabled();
    const debounceCall = timeoutSpy.mock.calls.find(([, delay]) => delay === 1000);
    expect(debounceCall).toBeTruthy();
    timeoutSpy.mockRestore();
  });

  it('waits for consent before starting invite', async () => {
    mockedBGCStatus.mockResolvedValueOnce({ status: 'failed', env: 'sandbox' });
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
      .mockResolvedValueOnce({ status: 'failed', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'failed', env: 'sandbox' });

    mockedBGCInvite.mockResolvedValue({
      ok: true,
      status: 'failed',
      report_id: 'RPT-2',
      already_in_progress: true,
    });

    render(<BGCStep instructorId="instructor-789" />);

    const button = await screen.findByRole('button', { name: /start background check/i });
    await waitFor(() => expect(button).not.toBeDisabled());
    await userEvent.click(button);

    await waitFor(() => {
      expect(mockedBGCInvite).toHaveBeenCalledWith('instructor-789');
    });
    expect(toast.success).toHaveBeenCalledWith('Background check already in progress');
  });

  it('disables CTA and shows message when forbidden', async () => {
    mockedBGCStatus.mockResolvedValueOnce({ status: 'failed', env: 'sandbox' });
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

  it('polls pending status with backoff 15s→60s→300s then clears when passed', async () => {
    jest.useFakeTimers();
    mockedBGCStatus
      .mockResolvedValueOnce({ status: 'pending', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'pending', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'pending', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'passed', env: 'sandbox', completed_at: '2025-01-01T00:00:00Z' });

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
      .mockResolvedValueOnce({ status: 'review', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'review', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'review', env: 'sandbox' })
      .mockResolvedValueOnce({ status: 'passed', env: 'sandbox', completed_at: '2025-02-02T00:00:00Z' });

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
});
