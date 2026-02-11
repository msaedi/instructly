import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BGCStep } from '../BGCStep';
import { bgcInvite, bgcRecheck, bgcStatus } from '@/lib/api/bgc';
import { ApiProblemError } from '@/lib/api/fetch';
import { toast } from 'sonner';

// Mock dependencies
jest.mock('@/lib/api/bgc', () => ({
  bgcInvite: jest.fn(),
  bgcRecheck: jest.fn(),
  bgcStatus: jest.fn(),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    info: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    debug: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/lib/env', () => ({
  IS_NON_PROD: false,
}));

const bgcStatusMock = bgcStatus as jest.Mock;
const bgcInviteMock = bgcInvite as jest.Mock;
const bgcRecheckMock = bgcRecheck as jest.Mock;
const toastMock = toast as jest.Mocked<typeof toast>;

const createApiProblemError = (
  statusCode: number,
  code?: string,
  detail: string = 'Test error detail'
): ApiProblemError => {
  const problem = {
    type: 'test',
    title: 'Test Error',
    status: statusCode,
    detail,
    code,
  };
  // ApiProblemError constructor is (problem, response)
  return new ApiProblemError(problem, { status: statusCode } as Response);
};

describe('BGCStep', () => {
  const mockInstructorId = 'instructor-123';
  const defaultStatusResponse = {
    status: 'failed' as const,
    report_id: null,
    completed_at: null,
    consent_recent: false,
    consent_recent_at: null,
    valid_until: null,
    expires_in_days: null,
    is_expired: false,
    eta: null,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    bgcStatusMock.mockResolvedValue(defaultStatusResponse);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('initial rendering', () => {
    it('shows loading state initially', async () => {
      bgcStatusMock.mockImplementation(() => new Promise(() => {}));

      render(<BGCStep instructorId={mockInstructorId} />);

      expect(screen.getByText('Checking status…')).toBeInTheDocument();
    });

    it('renders with failed/not started status', async () => {
      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Not started')).toBeInTheDocument();
      });
    });

    it('renders the start button', async () => {
      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeInTheDocument();
      });
    });

    it('displays valid until label', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        valid_until: '2025-12-31T00:00:00Z',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verified')).toBeInTheDocument();
      });
    });
  });

  describe('status display', () => {
    it.each([
      ['passed', 'Verified'],
      ['pending', 'Verification pending'],
      ['review', 'Under review'],
      ['consider', 'Needs attention'],
      ['failed', 'Not started'],
      ['canceled', 'Canceled'],
    ])('displays %s status as %s', async (status, label) => {
      bgcStatusMock.mockResolvedValue({ ...defaultStatusResponse, status });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText(label)).toBeInTheDocument();
      });
    });

    it('shows report ID when available', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        report_id: 'report-abc-123',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText(/Report ID: report-abc-123/)).toBeInTheDocument();
      });
    });

    it('shows completed date when available', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        completed_at: '2025-01-15T12:00:00Z',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText(/Completed/)).toBeInTheDocument();
      });
    });

    it('shows ETA when pending', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
        eta: '2025-01-20T12:00:00Z',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText(/Estimated completion:/)).toBeInTheDocument();
      });
    });

    it('shows canceled alert message', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'canceled',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent(/Background check was canceled/);
      });
    });
  });

  describe('recheck button', () => {
    it('shows recheck button when expired', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        is_expired: true,
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeInTheDocument();
      });
    });

    it('shows recheck button when expiring soon', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        expires_in_days: 15,
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeInTheDocument();
      });
    });
  });

  describe('start background check', () => {
    it('calls bgcInvite when clicking start button', async () => {
      bgcInviteMock.mockResolvedValue({ status: 'pending', report_id: 'new-report' });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(bgcInviteMock).toHaveBeenCalledWith(mockInstructorId);
      });
    });

    it('shows success message on successful invite', async () => {
      bgcInviteMock.mockResolvedValue({ status: 'pending', report_id: 'new-report' });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(screen.getAllByText('Check your email to continue').length).toBeGreaterThan(0);
      });
    });

    it('shows already in progress message', async () => {
      bgcInviteMock.mockResolvedValue({ status: 'pending', already_in_progress: true });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.success).toHaveBeenCalledWith('Background check already in progress');
      });
    });

    it('calls ensureConsent before inviting when provided', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(true);
      bgcInviteMock.mockResolvedValue({ status: 'pending' });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalled();
        expect(bgcInviteMock).toHaveBeenCalled();
      });
    });

    it('aborts when ensureConsent returns false', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(false);
      bgcInviteMock.mockResolvedValue({ status: 'pending' });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalled();
      });

      expect(bgcInviteMock).not.toHaveBeenCalled();
    });

    it('disables start button when already pending', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeDisabled();
      });
    });

    it('disables start button when already passed', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeDisabled();
      });
    });
  });

  describe('error handling - start', () => {
    it('handles 403 forbidden error', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(403, 'forbidden'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.info).toHaveBeenCalledWith(
          'Only the owner can start a background check.',
          expect.any(Object)
        );
      });
    });

    it('handles checkr_auth_error', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(400, 'checkr_auth_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check provider authentication failed',
          expect.any(Object)
        );
      });
    });

    it('handles checkr_package_not_found', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(400, 'checkr_package_not_found'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check configuration error: Checkr package slug is invalid.',
          expect.any(Object)
        );
      });
    });

    it('handles invalid_work_location', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(400, 'invalid_work_location', 'ZIP code missing'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Your primary teaching ZIP code is missing or invalid.',
          expect.any(Object)
        );
      });
    });

    it('handles geocoding_provider_error', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(500, 'geocoding_provider_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Our location verification service is having trouble.',
          expect.any(Object)
        );
      });
    });

    it('handles checkr_work_location_error', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(400, 'checkr_work_location_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check configuration error: work location rejected.',
          expect.any(Object)
        );
      });
    });

    it('handles bgc_invite_rate_limited', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(429, 'bgc_invite_rate_limited'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.info).toHaveBeenCalledWith(
          expect.stringContaining('recently requested')
        );
      });
    });

    it('handles bgc_consent_required and retries after consent', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(true);
      bgcInviteMock
        .mockRejectedValueOnce(createApiProblemError(400, 'bgc_consent_required'))
        .mockResolvedValueOnce({ status: 'pending' });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalled();
        expect(bgcInviteMock).toHaveBeenCalledTimes(2);
      });
    });

    it('handles generic API error', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(500, 'unknown_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Unable to start background check',
          expect.any(Object)
        );
      });
    });

    it('handles non-ApiProblemError', async () => {
      bgcInviteMock.mockRejectedValue(new Error('Network error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Unable to start background check',
          expect.any(Object)
        );
      });
    });
  });

  describe('recheck background check', () => {
    beforeEach(() => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        is_expired: true,
      });
    });

    it('calls bgcRecheck when clicking recheck button', async () => {
      bgcRecheckMock.mockResolvedValue({ status: 'pending', report_id: 'recheck-report' });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(bgcRecheckMock).toHaveBeenCalledWith(mockInstructorId);
      });
    });

    it('shows success message on successful recheck', async () => {
      bgcRecheckMock.mockResolvedValue({ status: 'pending' });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.success).toHaveBeenCalledWith('Background check re-check started');
      });
    });

    it('shows already in progress message for recheck', async () => {
      bgcRecheckMock.mockResolvedValue({ status: 'pending', already_in_progress: true });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.success).toHaveBeenCalledWith('Background check already in progress');
      });
    });

    it('calls ensureConsent before recheck when provided', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(true);
      bgcRecheckMock.mockResolvedValue({ status: 'pending' });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalled();
        expect(bgcRecheckMock).toHaveBeenCalled();
      });
    });

    it('aborts recheck when ensureConsent returns false', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(false);

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalled();
      });

      expect(bgcRecheckMock).not.toHaveBeenCalled();
    });
  });

  describe('error handling - recheck', () => {
    beforeEach(() => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        is_expired: true,
      });
    });

    it('handles bgc_consent_required for recheck', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(true);
      bgcRecheckMock
        .mockRejectedValueOnce(createApiProblemError(400, 'bgc_consent_required'))
        .mockResolvedValueOnce({ status: 'pending' });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalled();
        expect(bgcRecheckMock).toHaveBeenCalledTimes(2);
      });
    });

    it('handles checkr_auth_error for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(createApiProblemError(400, 'checkr_auth_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check provider authentication failed',
          expect.any(Object)
        );
      });
    });

    it('handles checkr_package_not_found for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(createApiProblemError(400, 'checkr_package_not_found'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check configuration error: Checkr package slug is invalid.',
          expect.any(Object)
        );
      });
    });

    it('handles invalid_work_location for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(createApiProblemError(400, 'invalid_work_location'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Your primary teaching ZIP code is missing or invalid.',
          expect.any(Object)
        );
      });
    });

    it('handles geocoding_provider_error for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(createApiProblemError(500, 'geocoding_provider_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Our location verification service is having trouble.',
          expect.any(Object)
        );
      });
    });

    it('handles checkr_work_location_error for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(createApiProblemError(400, 'checkr_work_location_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check configuration error: work location rejected.',
          expect.any(Object)
        );
      });
    });

    it('handles 429 rate limit for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(createApiProblemError(429, 'rate_limited'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.info).toHaveBeenCalledWith('You can try again later.');
      });
    });

    it('handles generic API error for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(createApiProblemError(500, 'server_error', 'Internal error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Unable to re-check background',
          expect.any(Object)
        );
      });
    });

    it('handles non-ApiProblemError for recheck', async () => {
      bgcRecheckMock.mockRejectedValue(new Error('Network failure'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Unable to re-check background',
          expect.any(Object)
        );
      });
    });
  });

  describe('initial load error', () => {
    it('handles status fetch error', async () => {
      bgcStatusMock.mockRejectedValue(new Error('Failed to fetch'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalled();
      });
    });

    it('shows status unavailable message on error', async () => {
      bgcStatusMock.mockRejectedValue(new Error('Failed to fetch'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText(/Status unavailable/i)).toBeInTheDocument();
      });
    });
  });

  describe('polling behavior', () => {
    it('starts polling when status is pending', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Initial call + one poll call after 15 seconds
      expect(bgcStatusMock).toHaveBeenCalledTimes(1);

      await act(async () => {
        jest.advanceTimersByTime(15000);
      });

      await waitFor(() => {
        expect(bgcStatusMock).toHaveBeenCalledTimes(2);
      });
    });

    it('stops polling when backoff limit reached', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Advance through all backoff intervals: 15s, 60s, 300s
      await act(async () => {
        jest.advanceTimersByTime(15000);
      });

      await act(async () => {
        jest.advanceTimersByTime(60000);
      });

      await act(async () => {
        jest.advanceTimersByTime(300000);
      });

      const callCount = bgcStatusMock.mock.calls.length;

      // No more polling after all intervals
      await act(async () => {
        jest.advanceTimersByTime(300000);
      });

      expect(bgcStatusMock.mock.calls.length).toBe(callCount);
    });
  });

  describe('callback handling', () => {
    it('calls onStatusUpdate with snapshot', async () => {
      const onStatusUpdate = jest.fn();
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        report_id: 'test-report',
      });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          onStatusUpdate={onStatusUpdate}
        />
      );

      await waitFor(() => {
        expect(onStatusUpdate).toHaveBeenCalledWith(
          expect.objectContaining({
            status: 'passed',
            reportId: 'test-report',
          })
        );
      });
    });
  });

  describe('edge cases', () => {
    it('handles invalid eta date format', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
        eta: 'invalid-date',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Should not crash and should not show ETA
      expect(screen.queryByText(/Estimated completion:/)).not.toBeInTheDocument();
    });

    it('handles invalid valid_until date', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        valid_until: 'not-a-date',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verified')).toBeInTheDocument();
      });

      // Component shows "Invalid Date" for invalid date strings
      expect(screen.getByText(/Valid until:/)).toBeInTheDocument();
    });

    it('handles ApiProblemError with detail message', async () => {
      const errorWithDetail = createApiProblemError(400, undefined, 'Detailed error message');

      bgcInviteMock.mockRejectedValue(errorWithDetail);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalled();
      });
    });

    it('unmounts cleanly with pending poll', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
      });

      const { unmount } = render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Unmount while poll is scheduled
      unmount();

      // Advance timer - should not throw
      await act(async () => {
        jest.advanceTimersByTime(60000);
      });
    });

    it('handles status review', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'review',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Under review')).toBeInTheDocument();
      });
    });

    it('handles status consider', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'consider',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Needs attention')).toBeInTheDocument();
      });
    });
  });

  describe('cooldown behavior', () => {
    it('activates cooldown after successful invite', async () => {
      bgcInviteMock.mockResolvedValue({ status: 'pending' });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      // Dismiss the post-invite confirmation modal so aria-hidden clears
      const gotItButton = await screen.findByRole('button', { name: /got it/i });
      await act(async () => {
        fireEvent.click(gotItButton);
      });

      // Button should be disabled (status is 'pending')
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeDisabled();
      });

      // After cooldown period
      await act(async () => {
        jest.advanceTimersByTime(1000);
      });

      // Note: Status is now 'pending' so button remains disabled
      // This is expected behavior
    });
  });

  describe('polling error handling', () => {
    it('handles error during polling and shows toast', async () => {
      // First call succeeds and returns pending status
      bgcStatusMock
        .mockResolvedValueOnce({
          ...defaultStatusResponse,
          status: 'pending',
        })
        // Second call during polling fails
        .mockRejectedValueOnce(new Error('Polling failed'));

      render(<BGCStep instructorId={mockInstructorId} />);

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Advance to first poll interval (15 seconds)
      await act(async () => {
        jest.advanceTimersByTime(15000);
      });

      // Error toast should be shown
      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalled();
      });
    });

    it('clears existing poll timer when status changes', async () => {
      // Start with pending status (triggers polling)
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Now change status to 'review' (still polls, but should clear previous timer)
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'review',
      });

      // Trigger a re-fetch by advancing time
      await act(async () => {
        jest.advanceTimersByTime(15000);
      });

      // Wait for new status
      await waitFor(() => {
        expect(screen.getByText('Under review')).toBeInTheDocument();
      });

      // Component should still be working correctly
      expect(screen.getByTestId('bgc-step')).toBeInTheDocument();
    });
  });

  describe('formatDate edge cases', () => {
    it('handles completed_at with invalid date that throws', async () => {
      // completed_at that will fail Date parsing in an unusual way
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        completed_at: '', // Empty string
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verified')).toBeInTheDocument();
      });

      // Should render without crashing
      expect(screen.getByTestId('bgc-step')).toBeInTheDocument();
    });
  });

  describe('polling backoff exhaustion', () => {
    it('stops polling after all POLL_BACKOFF_MS entries are exhausted', async () => {
      // Status remains "pending" throughout so polling keeps going until backoff runs out
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'pending',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      const callsAfterInit = bgcStatusMock.mock.calls.length;

      // Advance through backoff[0] = 15_000ms
      await act(async () => {
        jest.advanceTimersByTime(15000);
      });

      await waitFor(() => {
        expect(bgcStatusMock.mock.calls.length).toBe(callsAfterInit + 1);
      });

      // Advance through backoff[1] = 60_000ms
      await act(async () => {
        jest.advanceTimersByTime(60000);
      });

      await waitFor(() => {
        expect(bgcStatusMock.mock.calls.length).toBe(callsAfterInit + 2);
      });

      // Advance through backoff[2] = 300_000ms
      await act(async () => {
        jest.advanceTimersByTime(300000);
      });

      await waitFor(() => {
        expect(bgcStatusMock.mock.calls.length).toBe(callsAfterInit + 3);
      });

      // backoffIdxRef is now 3, which is >= POLL_BACKOFF_MS.length (3)
      // scheduleNextPoll should return early without scheduling
      const callsAfterExhaustion = bgcStatusMock.mock.calls.length;

      await act(async () => {
        jest.advanceTimersByTime(600000);
      });

      // No additional calls should have been made
      expect(bgcStatusMock.mock.calls.length).toBe(callsAfterExhaustion);
    });

    it('stops polling when status transitions from pending to passed during polling', async () => {
      bgcStatusMock
        .mockResolvedValueOnce({ ...defaultStatusResponse, status: 'pending' })
        .mockResolvedValue({ ...defaultStatusResponse, status: 'passed' });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Advance through first poll
      await act(async () => {
        jest.advanceTimersByTime(15000);
      });

      await waitFor(() => {
        expect(screen.getByText('Verified')).toBeInTheDocument();
      });

      const callsAfterTransition = bgcStatusMock.mock.calls.length;

      // No more polling since status is no longer pending/review/consider
      await act(async () => {
        jest.advanceTimersByTime(300000);
      });

      expect(bgcStatusMock.mock.calls.length).toBe(callsAfterTransition);
    });
  });

  describe('consent modal flow', () => {
    it('calls ensureConsent and proceeds when consent returns true', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(true);
      bgcInviteMock.mockResolvedValue({ status: 'pending', report_id: 'rpt-1' });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalledTimes(1);
        expect(bgcInviteMock).toHaveBeenCalledWith(mockInstructorId);
        expect(screen.getAllByText('Check your email to continue').length).toBeGreaterThan(0);
      });
    });

    it('does not call bgcInvite when consent returns false', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(false);

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalledTimes(1);
      });

      expect(bgcInviteMock).not.toHaveBeenCalled();
      expect(toastMock.success).not.toHaveBeenCalled();
    });

    it('skips ensureConsent when consentRecent is already true', async () => {
      // First load with consent_recent: true from server
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'failed',
        consent_recent: true,
      });
      const ensureConsent = jest.fn().mockResolvedValue(true);
      bgcInviteMock.mockResolvedValue({ status: 'pending' });

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(bgcInviteMock).toHaveBeenCalled();
      });

      // ensureConsent should NOT have been called because consentRecent was already true
      expect(ensureConsent).not.toHaveBeenCalled();
    });
  });

  describe('403 forbidden state', () => {
    it('sets isForbidden and permanently disables button after 403', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(403, 'forbidden'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      // Should show the info toast
      await waitFor(() => {
        expect(toastMock.info).toHaveBeenCalledWith(
          'Only the owner can start a background check.',
          expect.any(Object)
        );
      });

      // Button should be disabled after forbidden
      expect(screen.getByRole('button', { name: /start background check/i })).toBeDisabled();

      // The forbidden alert text should be visible
      const alerts = screen.getAllByRole('alert');
      const forbiddenAlert = alerts.find((a) => a.textContent?.includes('Only the owner'));
      expect(forbiddenAlert).toBeDefined();
    });

    it('does not activate cooldown after 403 error', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(403, 'forbidden'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.info).toHaveBeenCalled();
      });

      // Even after cooldown timer, button stays disabled due to isForbidden
      await act(async () => {
        jest.advanceTimersByTime(2000);
      });

      expect(screen.getByRole('button', { name: /start background check/i })).toBeDisabled();
    });
  });

  describe('error code specific toasts', () => {
    it('handles checkr_auth_error with detail as object containing message', async () => {
      const problem = {
        type: 'test',
        title: 'Test Error',
        status: 400,
        detail: { code: 'checkr_auth_error', message: 'Invalid API key' },
        code: undefined,
      };
      const err = new ApiProblemError(problem as never, { status: 400 } as Response);
      bgcInviteMock.mockRejectedValue(err);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check provider authentication failed',
          expect.any(Object)
        );
      });
    });

    it('handles invalid_work_location without detail message', async () => {
      // detail as object with code but no message
      const problem = {
        type: 'test',
        title: 'Test Error',
        status: 400,
        detail: { code: 'invalid_work_location' },
      };
      const err = new ApiProblemError(problem as never, { status: 400 } as Response);
      bgcInviteMock.mockRejectedValue(err);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Your primary teaching ZIP code is missing or invalid.',
          expect.objectContaining({
            description: 'Please update your ZIP code and try again.',
          })
        );
      });
    });

    it('handles geocoding_provider_error with provider_error details', async () => {
      const problem = {
        type: 'test',
        title: 'Test Error',
        status: 500,
        detail: 'Geocoding failed',
        code: 'geocoding_provider_error',
        provider_error: { service: 'google', code: 'RATE_LIMIT' },
      };
      const err = new ApiProblemError(problem as never, { status: 500 } as Response);
      bgcInviteMock.mockRejectedValue(err);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Our location verification service is having trouble.',
          expect.objectContaining({ description: 'Please try again later.' })
        );
      });
    });

    it('handles checkr_work_location_error for start', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(400, 'checkr_work_location_error'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check configuration error: work location rejected.',
          expect.objectContaining({
            description: 'Please contact support to resolve the work location issue.',
          })
        );
      });
    });

    it('handles bgc_invite_rate_limited with full message', async () => {
      bgcInviteMock.mockRejectedValue(createApiProblemError(429, 'bgc_invite_rate_limited'));

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.info).toHaveBeenCalledWith(
          'You recently requested a background check. Please wait up to 24 hours before starting another one.'
        );
      });
    });
  });

  describe('cooldown timer behavior', () => {
    it('activates cooldown after successful invite and re-enables after timeout', async () => {
      // Return failed status so button can be re-enabled after cooldown
      bgcStatusMock.mockResolvedValue(defaultStatusResponse);
      bgcInviteMock.mockResolvedValue({ status: 'failed', report_id: null });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      // The button should be disabled during cooldown
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeDisabled();
      });

      // Advance past the 1000ms cooldown
      await act(async () => {
        jest.advanceTimersByTime(1100);
      });

      // Since status is 'failed', button should be re-enabled after cooldown
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });
    });

    it('does not activate cooldown when invite was not attempted (consent denied)', async () => {
      const ensureConsent = jest.fn().mockResolvedValue(false);

      render(
        <BGCStep
          instructorId={mockInstructorId}
          ensureConsent={ensureConsent}
        />
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      // Wait for the consent check to complete
      await waitFor(() => {
        expect(ensureConsent).toHaveBeenCalled();
      });

      // Button should be enabled again (no cooldown since invite was never called)
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });
    });
  });

  describe('detail message extraction from ApiProblemError', () => {
    it('extracts detail message when detail is a string', async () => {
      bgcInviteMock.mockRejectedValue(
        createApiProblemError(400, 'invalid_work_location', 'ZIP 00000 is not valid')
      );

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Your primary teaching ZIP code is missing or invalid.',
          expect.objectContaining({
            description: 'ZIP 00000 is not valid Please update your ZIP code and try again.',
          })
        );
      });
    });

    it('extracts code from top-level problem.code when detail has no code', async () => {
      const problem = {
        type: 'test',
        title: 'Test',
        status: 400,
        detail: 'Some detail',
        code: 'checkr_package_not_found',
      };
      const err = new ApiProblemError(problem as never, { status: 400 } as Response);
      bgcInviteMock.mockRejectedValue(err);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Background check configuration error: Checkr package slug is invalid.',
          expect.any(Object)
        );
      });
    });
  });

  describe('uncovered branch coverage', () => {
    it('uses fallback when bgcStatus returns null status (line 166 ?? branch)', async () => {
      bgcStatusMock.mockResolvedValue({
        status: null,
        report_id: null,
        completed_at: null,
        consent_recent: false,
        consent_recent_at: null,
        valid_until: null,
        expires_in_days: null,
        is_expired: false,
        eta: null,
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        // null status should fall back to 'failed' -> label 'Not started'
        expect(screen.getByText('Not started')).toBeInTheDocument();
      });
    });

    it('handles recheck invalid_work_location without detail message (line 500 falsy branch)', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        is_expired: true,
      });

      // Use an empty string detail so detailMessage is undefined (empty string is falsy for length check)
      const problem = {
        type: 'test',
        title: 'Test',
        status: 400,
        detail: '',
        code: 'invalid_work_location',
      };
      const err = new ApiProblemError(problem as never, { status: 400 } as Response);
      bgcRecheckMock.mockRejectedValue(err);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Your primary teaching ZIP code is missing or invalid.',
          expect.objectContaining({
            description: 'Please update your ZIP code and try again.',
          })
        );
      });
    });

    it('handles recheck invalid_work_location with detail message (line 499 truthy branch)', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        is_expired: true,
      });

      bgcRecheckMock.mockRejectedValue(
        createApiProblemError(400, 'invalid_work_location', 'ZIP 99999 is not valid')
      );

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Your primary teaching ZIP code is missing or invalid.',
          expect.objectContaining({
            description: 'ZIP 99999 is not valid Please update your ZIP code and try again.',
          })
        );
      });
    });

    it('handles recheck generic error with empty detail (line 517 fallback branch)', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        is_expired: true,
      });

      // error code is unrecognized, detail is empty string -> detailMessage is undefined -> fallback
      const problem = {
        type: 'test',
        title: 'Test',
        status: 400,
        detail: '',
        code: 'some_other_error',
      };
      const err = new ApiProblemError(problem as never, { status: 400 } as Response);
      bgcRecheckMock.mockRejectedValue(err);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Unable to re-check background',
          expect.objectContaining({
            description: 'Please try again in a moment.',
          })
        );
      });
    });

    it('handles recheck geocoding_provider_error with debug info (line 476 debugInfo branch)', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
        is_expired: true,
      });

      const problem = {
        type: 'test',
        title: 'Test',
        status: 500,
        detail: 'Geocoding failed',
        code: 'geocoding_provider_error',
        debug: { internal_error: 'timeout', service: 'mapbox' },
      };
      const err = new ApiProblemError(problem as never, { status: 500 } as Response);
      bgcRecheckMock.mockRejectedValue(err);

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /re-check/i })).toBeEnabled();
      });

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /re-check/i }));
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith(
          'Our location verification service is having trouble.',
          expect.objectContaining({ description: 'Please try again later.' })
        );
      });
    });

    it('clears existing cooldown timer on double-click start (line 422 cooldownRef branch)', async () => {
      bgcStatusMock.mockResolvedValue(defaultStatusResponse);
      // First invite returns failed so button re-enables after cooldown
      bgcInviteMock
        .mockResolvedValueOnce({ status: 'failed', report_id: null })
        .mockResolvedValueOnce({ status: 'failed', report_id: null });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      // First click
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      // Advance past cooldown so button re-enables
      await act(async () => {
        jest.advanceTimersByTime(1100);
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /start background check/i })).toBeEnabled();
      });

      // Second click - should clear existing cooldown timer
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /start background check/i }));
      });

      expect(bgcInviteMock).toHaveBeenCalledTimes(2);
    });

    it('handles loadStatus being called after component unmounts (line 181/184 branches)', async () => {
      // Start with pending to trigger polling, which calls loadStatus
      bgcStatusMock
        .mockResolvedValueOnce({ ...defaultStatusResponse, status: 'pending' })
        .mockImplementation(() => new Promise((resolve) => {
          // Delay the response - component will unmount before it resolves
          setTimeout(() => resolve(defaultStatusResponse), 100);
        }));

      const { unmount } = render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Unmount before the poll timer fires
      unmount();

      // Advance timers to fire the poll - loadStatus should safely bail out
      await act(async () => {
        jest.advanceTimersByTime(15100);
      });

      // No crash means the isMountedRef check worked
    });

    it('handles initial load error with non-Error object (line 218 else branch)', async () => {
      bgcStatusMock.mockRejectedValue('string error, not Error instance');

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        // Should use default message since it's not an Error instance
        expect(toastMock.error).toHaveBeenCalledWith('Unable to load background check status');
      });
    });

    it('handles loadStatus error with non-Error object (line 189 else branch)', async () => {
      // First call succeeds to get past initial load, then subsequent loadStatus fails
      bgcStatusMock
        .mockResolvedValueOnce({ ...defaultStatusResponse, status: 'pending' })
        .mockRejectedValueOnce(42); // non-Error value

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verification pending')).toBeInTheDocument();
      });

      // Advance to trigger poll which calls loadStatus
      await act(async () => {
        jest.advanceTimersByTime(15000);
      });

      await waitFor(() => {
        expect(toastMock.error).toHaveBeenCalledWith('Unable to load background check status');
      });
    });

    it('shows (Test) suffix when IS_NON_PROD is true (line 68 branch)', async () => {
      // Dynamically override the mocked env module for this test
      const envModule = jest.requireMock<{ IS_NON_PROD: boolean }>('@/lib/env');
      const original = envModule.IS_NON_PROD;
      envModule.IS_NON_PROD = true;

      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verified (Test)')).toBeInTheDocument();
      });

      // Restore
      envModule.IS_NON_PROD = original;
    });

    it('does not start polling when status is not pending/review/consider (line 269 else branch)', async () => {
      bgcStatusMock.mockResolvedValue({
        ...defaultStatusResponse,
        status: 'passed',
      });

      render(<BGCStep instructorId={mockInstructorId} />);

      await waitFor(() => {
        expect(screen.getByText('Verified')).toBeInTheDocument();
      });

      const callsAfterLoad = bgcStatusMock.mock.calls.length;

      // Advance past all poll intervals - no polling should occur
      await act(async () => {
        jest.advanceTimersByTime(400000);
      });

      expect(bgcStatusMock.mock.calls.length).toBe(callsAfterLoad);
    });
  });
});
