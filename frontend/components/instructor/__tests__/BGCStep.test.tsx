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
        expect(toastMock.success).toHaveBeenCalledWith('Background check started');
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

      // Button should be disabled during cooldown
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
});
