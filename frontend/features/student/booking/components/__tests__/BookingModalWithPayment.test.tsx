import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react-dom/test-utils';
import userEvent from '@testing-library/user-event';
import BookingModalWithPayment from '../BookingModalWithPayment';
import type { Instructor } from '../../types';
import { useAuth } from '../../hooks/useAuth';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/components/booking/CheckoutFlow', () => ({
  __esModule: true,
  default: ({ onSuccess, onCancel }: { onSuccess: (id: string) => void; onCancel: () => void }) => (
    <div>
      <button onClick={() => onSuccess('pi_123')}>Mock Success</button>
      <button onClick={onCancel}>Mock Cancel</button>
    </div>
  ),
}));

const useAuthMock = useAuth as jest.Mock;
const useRouterMock = useRouter as jest.Mock;

const instructor: Instructor = {
  user_id: 'instructor-1',
  user: { first_name: 'Jane', last_initial: 'D' },
  bio: 'Bio',
  service_area_boroughs: ['Manhattan'],
  service_area_summary: 'NYC',
  years_experience: 5,
  services: [
    { id: 'service-1', skill: 'Piano', hourly_rate: 100, duration_options: [60], duration: 60 },
  ],
};

const instructorMultipleServices: Instructor = {
  ...instructor,
  services: [
    { id: 'service-1', skill: 'Piano', hourly_rate: 100, duration_options: [60], duration: 60 },
    { id: 'service-2', skill: 'Guitar', hourly_rate: 80, duration_options: [30, 60], duration: 30 },
  ],
};

const renderModal = (props?: Partial<React.ComponentProps<typeof BookingModalWithPayment>>) => {
  const onClose = jest.fn();
  render(
    <BookingModalWithPayment
      isOpen
      onClose={onClose}
      instructor={instructor}
      selectedDate="2025-01-01"
      selectedTime="10:00"
      onContinueToBooking={jest.fn()}
      {...props}
    />
  );
  return { onClose };
};

const getTextInputs = () => screen.getAllByRole('textbox') as HTMLInputElement[];

describe('BookingModalWithPayment', () => {
  const pushMock = jest.fn();

  beforeEach(() => {
    useRouterMock.mockReturnValue({ push: pushMock });
    pushMock.mockReset();
    jest.spyOn(window, 'alert').mockImplementation(() => undefined);
    const storage: Record<string, string> = {};
    Object.defineProperty(window, 'sessionStorage', {
      value: {
        setItem: jest.fn((key: string, value: string) => {
          storage[key] = value;
        }),
        getItem: jest.fn((key: string) => storage[key] ?? null),
        removeItem: jest.fn((key: string) => {
          delete storage[key];
        }),
        clear: jest.fn(() => {
          Object.keys(storage).forEach((key) => delete storage[key]);
        }),
        key: jest.fn(),
        length: 0,
      },
      configurable: true,
    });
  });

  afterEach(() => {
    (window.alert as jest.Mock).mockRestore();
  });

  it('does not render when closed', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const { container } = render(
      <BookingModalWithPayment
        isOpen={false}
        onClose={jest.fn()}
        onContinueToBooking={jest.fn()}
        instructor={instructor}
        selectedDate="2025-01-01"
        selectedTime="10:00"
      />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('redirects unauthenticated users and stores booking intent', async () => {
    const redirectToLogin = jest.fn();
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin,
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    expect(redirectToLogin).toHaveBeenCalledWith('/student/booking/confirm');
    expect(window.sessionStorage.setItem).toHaveBeenCalled();
  });

  it('moves to booking details when authenticated', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    expect(screen.getByText('Booking Details')).toBeInTheDocument();
  });

  it('validates required fields before payment', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: '', email: '' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    expect(window.alert).toHaveBeenCalledWith('Please fill in all required fields');
  });

  it('completes payment flow and redirects after success', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    const { onClose } = renderModal();

    await user.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    const inputs = getTextInputs();
    expect(inputs.length).toBeGreaterThanOrEqual(3);
    const nameInput = inputs[0]!;
    const emailInput = inputs[1]!;
    const phoneInput = inputs[2]!;
    await user.clear(nameInput);
    await user.type(nameInput, 'Jane Doe');
    await user.clear(emailInput);
    await user.type(emailInput, 'jane@example.com');
    await user.type(phoneInput, '555-1111');
    await user.click(screen.getByRole('checkbox'));

    await user.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    await user.click(screen.getByRole('button', { name: 'Mock Success' }));

    await waitFor(() => {
      expect(screen.getAllByText('Booking Confirmed!').length).toBeGreaterThan(0);
    });

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
      expect(pushMock).toHaveBeenCalledWith('/student/dashboard');
    });

    jest.useRealTimers();
  });

  it('shows alert when terms not agreed', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    // Fill in all required fields but don't check terms
    const inputs = getTextInputs();
    const phoneInput = inputs[2]!;
    await userEvent.type(phoneInput, '555-1111');

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    expect(window.alert).toHaveBeenCalledWith('Please agree to the terms and cancellation policy');
  });

  it('handles back button from booking-details to select-time', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    // Go to booking details
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));
    expect(screen.getByText('Booking Details')).toBeInTheDocument();

    // Click back button
    await userEvent.click(screen.getByRole('button', { name: 'Go back' }));

    // Should be back at select-time
    expect(screen.getByText('Book Your Session')).toBeInTheDocument();
  });

  it('handles back button from payment to booking-details', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    // Go to booking details
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    // Fill form and go to payment
    const inputs = getTextInputs();
    const phoneInput = inputs[2]!;
    await userEvent.type(phoneInput, '555-1111');
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    // Should be at payment step
    expect(screen.getByText('Payment')).toBeInTheDocument();

    // Click back button
    await userEvent.click(screen.getByRole('button', { name: 'Go back' }));

    // Should be back at booking-details
    expect(screen.getByText('Booking Details')).toBeInTheDocument();
  });

  it('allows changing service selection in dropdown', async () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    renderModal({ instructor: instructorMultipleServices });

    // Find the service dropdown
    const dropdown = screen.getByRole('combobox');
    expect(dropdown).toBeInTheDocument();

    // Change to Guitar service
    await userEvent.selectOptions(dropdown, 'service-2');

    // Verify Guitar is selected (price should change from $100 to $40 for 30min)
    expect(screen.getByText(/\$40\.00 total/)).toBeInTheDocument();
  });

  it('allows entering notes in the booking form', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    // Go to booking details
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    // Find notes textarea (it's the only textarea in the form - 4th element after name, email, phone)
    const textboxes = screen.getAllByRole('textbox');
    const textarea = textboxes.find(el => el.tagName === 'TEXTAREA') as HTMLTextAreaElement;
    await userEvent.type(textarea, 'I want to learn jazz piano');

    expect(textarea).toHaveValue('I want to learn jazz piano');
  });

  it('handles cancel from payment step', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    // Go to booking details
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    // Fill form and go to payment
    const inputs = getTextInputs();
    const phoneInput = inputs[2]!;
    await userEvent.type(phoneInput, '555-1111');
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    // Click the mock cancel button in CheckoutFlow
    await userEvent.click(screen.getByRole('button', { name: 'Mock Cancel' }));

    // Should be back at booking-details
    expect(screen.getByText('Booking Details')).toBeInTheDocument();
  });

  it('displays session details with service area and price', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    // Should display service area
    expect(screen.getByText('NYC')).toBeInTheDocument();
    // Should display date and time
    expect(screen.getByText(/2025-01-01 at 10:00/)).toBeInTheDocument();
    // Should display price
    expect(screen.getByText(/\$100\.00 total/)).toBeInTheDocument();
  });

  it('closes modal and resets state when close button clicked', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    const { onClose } = renderModal();

    // Go to booking details
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));
    expect(screen.getByText('Booking Details')).toBeInTheDocument();

    // Close the modal
    await userEvent.click(screen.getByRole('button', { name: 'Close booking modal' }));

    expect(onClose).toHaveBeenCalled();
  });
});
