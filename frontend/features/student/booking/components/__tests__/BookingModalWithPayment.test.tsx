import { render, screen, waitFor, act } from '@testing-library/react';
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

  it('shows alert when selectedService is null during submit (lines 168-170)', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    // Create an instructor with no services so selectedService will be null
    const instructorNoServices: Instructor = {
      ...instructor,
      services: [],
    };

    renderModal({ instructor: instructorNoServices });

    // Go to booking details
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    // Fill in all required fields
    const inputs = getTextInputs();
    const phoneInput = inputs[2]!;
    await userEvent.type(phoneInput, '555-1111');
    await userEvent.click(screen.getByRole('checkbox'));

    // Click submit - should trigger the !selectedService alert
    await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

    expect(window.alert).toHaveBeenCalledWith('Please select a service');
  });

  it('handles service with non-numeric hourly_rate gracefully', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorBadRate: Instructor = {
      ...instructor,
      services: [
        {
          id: 'service-1',
          skill: 'Piano',
          hourly_rate: 'not_a_number' as unknown as number,
          duration_options: [60],
          duration: 60,
        },
      ],
    };

    renderModal({ instructor: instructorBadRate });

    // Should display $0.00 total since rate is NaN
    expect(screen.getByText(/\$0\.00 total/)).toBeInTheDocument();
  });

  it('handles user with null full_name and email', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: null, email: null },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    // Should show booking details form without crashing
    expect(screen.getByText('Booking Details')).toBeInTheDocument();
  });

  it('does not show back button on success step', async () => {
    jest.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: 'jane@example.com' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    await user.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    const inputs = getTextInputs();
    await user.clear(inputs[0]!);
    await user.type(inputs[0]!, 'Jane Doe');
    await user.clear(inputs[1]!);
    await user.type(inputs[1]!, 'jane@example.com');
    await user.type(inputs[2]!, '555-1111');
    await user.click(screen.getByRole('checkbox'));

    await user.click(screen.getByRole('button', { name: 'Continue to Payment' }));
    await user.click(screen.getByRole('button', { name: 'Mock Success' }));

    await waitFor(() => {
      expect(screen.getAllByText('Booking Confirmed!').length).toBeGreaterThan(0);
    });

    // Back button should NOT be shown on success step
    expect(screen.queryByRole('button', { name: 'Go back' })).not.toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(2000);
    });

    jest.useRealTimers();
  });

  it('does not show service dropdown when only one service', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    renderModal(); // Default instructor has 1 service

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('handles non-numeric hourly_rate gracefully', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorBadRate: Instructor = {
      ...instructor,
      services: [
        { id: 'service-1', skill: 'Piano', hourly_rate: 'not-a-number' as unknown as number, duration_options: [60], duration: 60 },
      ],
    };

    render(
      <BookingModalWithPayment
        isOpen
        onClose={jest.fn()}
        onContinueToBooking={jest.fn()}
        instructor={instructorBadRate}
        selectedDate="2025-01-01"
        selectedTime="10:00"
      />
    );

    // Should display $0.00 instead of NaN
    expect(screen.getByText('$0.00 total')).toBeInTheDocument();
  });

  it('displays price correctly for string hourly_rate', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorStringRate: Instructor = {
      ...instructor,
      services: [
        { id: 'service-1', skill: 'Piano', hourly_rate: '75' as unknown as number, duration_options: [60], duration: 60 },
      ],
    };

    render(
      <BookingModalWithPayment
        isOpen
        onClose={jest.fn()}
        onContinueToBooking={jest.fn()}
        instructor={instructorStringRate}
        selectedDate="2025-01-01"
        selectedTime="10:00"
      />
    );

    // Should parse "75" as 75 and display $75.00
    expect(screen.getByText('$75.00 total')).toBeInTheDocument();
  });

  it('renders service dropdown with multiple services and correct rates', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    renderModal({ instructor: instructorMultipleServices });

    const dropdown = screen.getByRole('combobox');
    expect(dropdown).toBeInTheDocument();

    // Both options should be listed
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('Piano');
    expect(options[0]).toHaveTextContent('$100/hr');
    expect(options[1]).toHaveTextContent('Guitar');
    expect(options[1]).toHaveTextContent('$80/hr');
  });

  it('stores freeCancellationUntil for standard bookings when unauthenticated', async () => {
    const redirectToLogin = jest.fn();
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin,
    });

    // Use a date far in the future so determineBookingType returns STANDARD
    renderModal({ selectedDate: '2099-06-15', selectedTime: '14:00' });

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    expect(redirectToLogin).toHaveBeenCalled();

    // Verify bookingData was stored with freeCancellationUntil
    const storedData = (window.sessionStorage.setItem as jest.Mock).mock.calls.find(
      (call: string[]) => call[0] === 'bookingData'
    );
    expect(storedData).toBeDefined();
    const parsed = JSON.parse(storedData![1] as string) as Record<string, unknown>;
    expect(parsed).toHaveProperty('freeCancellationUntil');
  });

  it('handles service with null hourly_rate via nullish coalescing (line 53)', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorNullRate: Instructor = {
      ...instructor,
      services: [
        {
          id: 'service-1',
          skill: 'Piano',
          hourly_rate: null as unknown as number,
          duration_options: [60],
          duration: 60,
        },
      ],
    };

    renderModal({ instructor: instructorNullRate });

    // rateRaw is null, typeof null !== 'number', String(null ?? '0') = '0', parseFloat('0') = 0
    expect(screen.getByText(/\$0\.00 total/)).toBeInTheDocument();
  });

  it('handles service with undefined hourly_rate via nullish coalescing (line 53)', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorUndefinedRate: Instructor = {
      ...instructor,
      services: [
        {
          id: 'service-1',
          skill: 'Piano',
          hourly_rate: undefined as unknown as number,
          duration_options: [60],
          duration: 60,
        },
      ],
    };

    renderModal({ instructor: instructorUndefinedRate });

    // rateRaw is undefined, ?? '0' triggers, parseFloat('0') = 0
    expect(screen.getByText(/\$0\.00 total/)).toBeInTheDocument();
  });

  it('falls back to serviceAreaDisplayFull when no boroughs', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorNoArea: Instructor = {
      ...instructor,
      service_area_boroughs: [],
      service_area_summary: 'Brooklyn Area',
    };

    renderModal({ instructor: instructorNoArea });

    // serviceAreaBoroughs is empty, so primaryServiceArea = serviceAreaDisplayFull
    expect(screen.getByText('Brooklyn Area')).toBeInTheDocument();
  });

  it('shows booking details when authenticated but user is null (line 147-150)', async () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

    // Should show booking details form even when user is null (the if(user) block skipped)
    expect(screen.getByText('Booking Details')).toBeInTheDocument();
  });

  it('does not change service when dropdown value does not match any service', async () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    renderModal({ instructor: instructorMultipleServices });

    const dropdown = screen.getByRole('combobox');

    // Directly fire a change event with a non-existent service ID
    // This exercises the `if (service)` guard at line 259
    const event = { target: { value: 'non-existent-id' } };
    // Use fireEvent to set a value that doesn't match any service
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.change(dropdown, event);

    // Price should remain the same as the initial service (Piano at $100/hr for 60 min)
    expect(screen.getByText(/\$100\.00 total/)).toBeInTheDocument();
  });

  it('falls back to NYC when getServiceAreaDisplay returns empty string', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorEmptyArea: Instructor = {
      ...instructor,
      service_area_boroughs: [],
      service_area_summary: '',
    };

    renderModal({ instructor: instructorEmptyArea });

    // getServiceAreaDisplay returns '' -> || 'NYC' triggers
    expect(screen.getByText('NYC')).toBeInTheDocument();
  });

  it('uses defaultDuration fallback of 60 when service has no duration', () => {
    useAuthMock.mockReturnValue({
      user: null,
      isAuthenticated: false,
      redirectToLogin: jest.fn(),
    });

    const instructorNoDuration: Instructor = {
      ...instructor,
      services: [
        {
          id: 'service-1',
          skill: 'Piano',
          hourly_rate: 120,
          duration_options: [60],
          duration: undefined as unknown as number,
        },
      ],
    };

    renderModal({ instructor: instructorNoDuration });

    // defaultDuration = defaultService?.duration ?? 60 = 60
    // totalPrice = 120 * (60/60) = 120
    expect(screen.getByText(/\$120\.00 total/)).toBeInTheDocument();
  });

  it('resets form data with user email fallback during handleClose', async () => {
    useAuthMock.mockReturnValue({
      user: { full_name: 'Jane Doe', email: '' },
      isAuthenticated: true,
      redirectToLogin: jest.fn(),
    });

    const { onClose } = renderModal();

    await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));
    expect(screen.getByText('Booking Details')).toBeInTheDocument();

    // Close to trigger resetState
    await userEvent.click(screen.getByRole('button', { name: 'Close booking modal' }));
    expect(onClose).toHaveBeenCalled();
  });
});
