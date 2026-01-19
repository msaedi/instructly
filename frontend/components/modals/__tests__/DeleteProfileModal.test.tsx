import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DeleteProfileModal from '../DeleteProfileModal';

// Mock the API functions
jest.mock('@/lib/api', () => ({
  fetchWithAuth: jest.fn(),
  API_ENDPOINTS: {
    INSTRUCTOR_PROFILE: '/api/v1/instructors/me',
  },
}));

// Mock the logger
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

const { fetchWithAuth } = jest.requireMock('@/lib/api');

describe('DeleteProfileModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onSuccess: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders when open', () => {
    render(<DeleteProfileModal {...defaultProps} />);

    expect(screen.getByText('Delete Instructor Profile')).toBeInTheDocument();
    expect(screen.getByText(/this action cannot be undone/i)).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(<DeleteProfileModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByText('Delete Instructor Profile')).not.toBeInTheDocument();
  });

  it('displays consequences of deletion', () => {
    render(<DeleteProfileModal {...defaultProps} />);

    expect(screen.getByText(/your instructor profile and bio/i)).toBeInTheDocument();
    expect(screen.getByText(/all your services and rates/i)).toBeInTheDocument();
    expect(screen.getByText(/your availability schedule/i)).toBeInTheDocument();
    expect(screen.getByText(/all pending and future bookings/i)).toBeInTheDocument();
    expect(screen.getByText(/your instructor reviews and ratings/i)).toBeInTheDocument();
  });

  it('shows student account preservation note', () => {
    render(<DeleteProfileModal {...defaultProps} />);

    expect(screen.getByText('Student Account Preserved')).toBeInTheDocument();
    expect(
      screen.getByText(/you will remain a student/i)
    ).toBeInTheDocument();
  });

  it('disables delete button until DELETE is typed', () => {
    render(<DeleteProfileModal {...defaultProps} />);

    const deleteButton = screen.getByRole('button', { name: /delete profile/i });
    expect(deleteButton).toBeDisabled();
  });

  it('enables delete button when DELETE is typed', async () => {
    const user = userEvent.setup();
    render(<DeleteProfileModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText(/type delete here/i), 'DELETE');

    const deleteButton = screen.getByRole('button', { name: /delete profile/i });
    expect(deleteButton).not.toBeDisabled();
  });

  it('shows error when confirm text is incorrect and submit attempted', async () => {
    const user = userEvent.setup();
    render(<DeleteProfileModal {...defaultProps} />);

    // Type incorrect text
    await user.type(screen.getByPlaceholderText(/type delete here/i), 'delete');

    // The button should still be disabled with incorrect case
    const deleteButton = screen.getByRole('button', { name: /delete profile/i });
    expect(deleteButton).toBeDisabled();
  });

  it('shows visual feedback when DELETE is correctly typed', async () => {
    const user = userEvent.setup();
    render(<DeleteProfileModal {...defaultProps} />);

    const input = screen.getByPlaceholderText(/type delete here/i);
    await user.type(input, 'DELETE');

    // Input should have green styling (indicating correct confirmation)
    expect(input).toHaveClass('border-green-300');
  });

  it('calls onClose when Cancel button is clicked', async () => {
    const user = userEvent.setup();
    render(<DeleteProfileModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('clears confirm text when Cancel is clicked', async () => {
    const user = userEvent.setup();
    render(<DeleteProfileModal {...defaultProps} />);

    const input = screen.getByPlaceholderText(/type delete here/i);
    await user.type(input, 'DELE');
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    // Reopen modal and check input is cleared
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('successfully deletes profile on API success', async () => {
    const user = userEvent.setup();
    fetchWithAuth.mockResolvedValueOnce({ ok: true });
    render(<DeleteProfileModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText(/type delete here/i), 'DELETE');
    await user.click(screen.getByRole('button', { name: /delete profile/i }));

    await waitFor(() => {
      expect(fetchWithAuth).toHaveBeenCalledWith('/api/v1/instructors/me', {
        method: 'DELETE',
      });
      expect(defaultProps.onSuccess).toHaveBeenCalled();
      expect(defaultProps.onClose).toHaveBeenCalled();
    });
  });

  it('shows loading state during deletion', async () => {
    const user = userEvent.setup();
    let resolveDelete: (value: { ok: boolean }) => void;
    fetchWithAuth.mockImplementation(
      () => new Promise((resolve) => (resolveDelete = resolve))
    );
    render(<DeleteProfileModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText(/type delete here/i), 'DELETE');
    await user.click(screen.getByRole('button', { name: /delete profile/i }));

    expect(screen.getByText(/deleting/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeDisabled();

    resolveDelete!({ ok: true });
  });

  it('shows error message on API failure', async () => {
    const user = userEvent.setup();
    fetchWithAuth.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockResolvedValue({ detail: 'Cannot delete profile' }),
    });
    render(<DeleteProfileModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText(/type delete here/i), 'DELETE');
    await user.click(screen.getByRole('button', { name: /delete profile/i }));

    await waitFor(() => {
      expect(screen.getByText('Cannot delete profile')).toBeInTheDocument();
    });

    expect(defaultProps.onSuccess).not.toHaveBeenCalled();
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('shows fallback error message when API error has no detail', async () => {
    const user = userEvent.setup();
    fetchWithAuth.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockResolvedValue({}),
    });
    render(<DeleteProfileModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText(/type delete here/i), 'DELETE');
    await user.click(screen.getByRole('button', { name: /delete profile/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to delete profile/i)).toBeInTheDocument();
    });
  });

  it('handles network errors gracefully', async () => {
    const user = userEvent.setup();
    fetchWithAuth.mockRejectedValueOnce(new Error('Network error'));
    render(<DeleteProfileModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText(/type delete here/i), 'DELETE');
    await user.click(screen.getByRole('button', { name: /delete profile/i }));

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('clears error when user starts typing', async () => {
    const user = userEvent.setup();
    fetchWithAuth.mockResolvedValueOnce({
      ok: false,
      json: jest.fn().mockResolvedValue({ detail: 'Error occurred' }),
    });
    render(<DeleteProfileModal {...defaultProps} />);

    // Trigger error
    await user.type(screen.getByPlaceholderText(/type delete here/i), 'DELETE');
    await user.click(screen.getByRole('button', { name: /delete profile/i }));

    await waitFor(() => {
      expect(screen.getByText('Error occurred')).toBeInTheDocument();
    });

    // Clear the input and type again
    await user.clear(screen.getByPlaceholderText(/type delete here/i));
    await user.type(screen.getByPlaceholderText(/type delete here/i), 'D');

    expect(screen.queryByText('Error occurred')).not.toBeInTheDocument();
  });

  it('shows case-sensitive confirmation hint', () => {
    render(<DeleteProfileModal {...defaultProps} />);

    expect(screen.getByText(/this confirmation is case-sensitive/i)).toBeInTheDocument();
  });

  it('has proper accessibility attributes', () => {
    render(<DeleteProfileModal {...defaultProps} />);

    const input = screen.getByPlaceholderText(/type delete here/i);
    expect(input).toHaveAttribute('aria-describedby', 'delete-confirmation-help');
  });
});
