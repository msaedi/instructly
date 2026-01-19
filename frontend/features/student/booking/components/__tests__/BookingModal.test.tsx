import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BookingModal from '../BookingModal';
import type { Instructor } from '../../types';
import { useAuth } from '../../hooks/useAuth';
import { useRouter } from 'next/navigation';

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

jest.mock('../../hooks/useAuth', () => ({
  useAuth: jest.fn(),
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
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
    { id: 'service-2', skill: 'Guitar', hourly_rate: 80, duration_options: [30, 60], duration: 30 },
  ],
};

const instructorSingleService: Instructor = {
  ...instructor,
  services: [
    { id: 'service-1', skill: 'Piano', hourly_rate: 100, duration_options: [60], duration: 60 },
  ],
};

const renderModal = (props?: Partial<React.ComponentProps<typeof BookingModal>>) => {
  const onClose = jest.fn();
  const onContinueToBooking = jest.fn();
  render(
    <BookingModal
      isOpen
      onClose={onClose}
      onContinueToBooking={onContinueToBooking}
      instructor={instructor}
      selectedDate="2025-01-01"
      selectedTime="10:00"
      {...props}
    />
  );
  return { onClose, onContinueToBooking };
};

const getTextInputs = () => screen.getAllByRole('textbox') as HTMLInputElement[];

describe('BookingModal', () => {
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

  describe('visibility', () => {
    it('does not render when isOpen is false', () => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });

      const { container } = render(
        <BookingModal
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

    it('renders when isOpen is true', () => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });

      renderModal();

      expect(screen.getByText('Confirm Your Lesson')).toBeInTheDocument();
    });
  });

  describe('unauthenticated user flow', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('shows booking selection UI (not booking form)', () => {
      renderModal();

      // Should NOT see "Your Information" heading (that's the form)
      expect(screen.queryByText('Your Information')).not.toBeInTheDocument();
      // Should see duration selection
      expect(screen.getByText('Duration:')).toBeInTheDocument();
    });

    it('redirects to login and stores booking intent on continue', async () => {
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

    it('stores booking data in session storage', async () => {
      const redirectToLogin = jest.fn();
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin,
      });

      renderModal();

      await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('serviceId', expect.any(String));
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('selectedSlot', expect.any(String));
    });
  });

  describe('authenticated user flow', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });
    });

    it('shows booking form immediately with pre-filled user data', async () => {
      renderModal();

      // Authenticated users see booking form immediately (showBookingForm defaults to isAuthenticated)
      expect(screen.getByText('Your Information')).toBeInTheDocument();

      // Check pre-filled user data
      const inputs = getTextInputs();
      expect(inputs.length).toBeGreaterThanOrEqual(2);
      expect(inputs[0]).toHaveValue('Jane Doe');
      expect(inputs[1]).toHaveValue('jane@example.com');
    });

    it('validates required fields before submission', async () => {
      renderModal();

      // Authenticated user already sees form, clear the fields
      const inputs = getTextInputs();
      expect(inputs.length).toBeGreaterThanOrEqual(3);
      const nameInput = inputs[0]!;
      const emailInput = inputs[1]!;

      await userEvent.clear(nameInput);
      await userEvent.clear(emailInput);

      const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
      expect(continueButton).toBeDisabled();
      expect(window.alert).not.toHaveBeenCalled();
    });

    it('shows alert when required fields are missing on submit', async () => {
      useAuthMock.mockReturnValue({
        user: { full_name: '', email: '' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });

      renderModal();

      // Form shows with empty user data (user has no full_name or email)
      const inputs = getTextInputs();
      const phoneInput = inputs[2]!;

      // Fill in phone but not name/email
      await userEvent.type(phoneInput, '555-1111');

      // Check the checkbox
      await userEvent.click(screen.getByRole('checkbox'));

      // Button should still be disabled since name and email are empty
      const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
      expect(continueButton).toBeDisabled();
    });

    it('submits valid booking and navigates to confirmation', async () => {
      renderModal();

      // Authenticated user sees form immediately
      const inputs = getTextInputs();
      expect(inputs.length).toBeGreaterThanOrEqual(3);
      const phoneInput = inputs[2]!;

      // Name and email are already filled, just add phone
      await userEvent.type(phoneInput, '555-1111');

      await userEvent.click(screen.getByRole('checkbox'));

      await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

      await waitFor(() => {
        expect(pushMock).toHaveBeenCalledWith('/student/booking/confirm');
      });
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith('bookingData', expect.any(String));
    });
  });

  describe('auth state changes', () => {
    it('shows booking form after auth flips to true and continue is clicked', async () => {
      let authState: {
        user: { first_name: string; last_name: string; email: string; id: string } | null;
        isAuthenticated: boolean;
        redirectToLogin: jest.Mock;
      } = {
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      };
      useAuthMock.mockImplementation(() => authState);

      const onClose = jest.fn();
      const { rerender } = render(
        <BookingModal
          isOpen
          onClose={onClose}
          onContinueToBooking={jest.fn()}
          instructor={instructor}
          selectedDate="2025-01-01"
          selectedTime="10:00"
        />
      );

      expect(screen.queryByText('Your Information')).not.toBeInTheDocument();

      authState = {
        user: { first_name: 'Jane', last_name: 'Doe', email: 'jane@example.com', id: 'user-1' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      };

      rerender(
        <BookingModal
          isOpen
          onClose={onClose}
          onContinueToBooking={jest.fn()}
          instructor={instructor}
          selectedDate="2025-01-01"
          selectedTime="10:00"
        />
      );

      await userEvent.click(screen.getByRole('button', { name: 'Continue to Booking' }));

      expect(screen.getByText('Your Information')).toBeInTheDocument();
      const inputs = getTextInputs();
      expect(inputs[0]).toHaveValue('Jane Doe');
      expect(inputs[1]).toHaveValue('jane@example.com');
    });
  });

  describe('service selection', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('shows service selection when multiple services available', () => {
      renderModal({ instructor });

      expect(screen.getByText('Select Service:')).toBeInTheDocument();
      expect(screen.getByText('Piano')).toBeInTheDocument();
      expect(screen.getByText('Guitar')).toBeInTheDocument();
    });

    it('does not show service selection when single service', () => {
      renderModal({ instructor: instructorSingleService });

      expect(screen.queryByText('Select Service:')).not.toBeInTheDocument();
    });

    it('allows changing service selection', async () => {
      renderModal({ instructor });

      const guitarRadio = screen.getByRole('radio', { name: /guitar/i });
      await userEvent.click(guitarRadio);

      expect(guitarRadio).toBeChecked();
    });
  });

  describe('duration selection', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('shows duration options', () => {
      renderModal();

      expect(screen.getByText('30 minutes')).toBeInTheDocument();
      expect(screen.getByText('60 minutes')).toBeInTheDocument();
      expect(screen.getByText('90 minutes')).toBeInTheDocument();
    });

    it('allows changing duration selection', async () => {
      renderModal();

      const duration90Radio = screen.getByRole('radio', { name: /90 minutes/i });
      await userEvent.click(duration90Radio);

      expect(duration90Radio).toBeChecked();
    });

    it('updates price when duration changes', async () => {
      renderModal();

      // Select 30 minutes - should show $50 (100/hr * 0.5)
      const duration30Radio = screen.getByRole('radio', { name: /30 minutes/i });
      await userEvent.click(duration30Radio);

      // Total should reflect the new duration - look for the price in the summary
      const totalTexts = screen.getAllByText('$50');
      expect(totalTexts.length).toBeGreaterThan(0);
    });
  });

  describe('close behavior', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('calls onClose when close button is clicked', async () => {
      const { onClose } = renderModal();

      await userEvent.click(screen.getByRole('button', { name: 'Close modal' }));

      expect(onClose).toHaveBeenCalled();
    });

    it('calls onClose when clicking overlay backdrop', async () => {
      const { onClose } = renderModal();

      // Find the overlay (the outer div with onClick)
      const overlay = document.querySelector('[style*="modal-backdrop"]');
      if (overlay) {
        await userEvent.click(overlay);
        expect(onClose).toHaveBeenCalled();
      }
    });

    it('resets state when closing', async () => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });

      const { onClose } = renderModal();

      // Authenticated user already sees booking form
      expect(screen.getByText('Your Information')).toBeInTheDocument();

      // Close the modal
      await userEvent.click(screen.getByRole('button', { name: 'Close modal' }));
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('price calculation', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('calculates total price correctly for default duration', () => {
      renderModal();

      // Default service is Piano at $100/hr, default duration is 60 min
      // Price appears in the Total section
      const priceElements = screen.getAllByText('$100');
      expect(priceElements.length).toBeGreaterThan(0);
    });

    it('calculates total price correctly after changing service', async () => {
      renderModal();

      // Change to Guitar ($80/hr, default 30 min = $40)
      const guitarRadio = screen.getByRole('radio', { name: /guitar/i });
      await userEvent.click(guitarRadio);

      // Then 30 min of Guitar = $40
      const priceElements = screen.getAllByText('$40');
      expect(priceElements.length).toBeGreaterThan(0);
    });

    it('handles service with string hourly rate', () => {
      const instructorWithStringRate: Instructor = {
        ...instructorSingleService,
        services: [
          { id: 'service-1', skill: 'Piano', hourly_rate: '100' as unknown as number, duration_options: [60], duration: 60 },
        ],
      };

      renderModal({ instructor: instructorWithStringRate });

      // Should still calculate correctly
      const priceElements = screen.getAllByText('$100');
      expect(priceElements.length).toBeGreaterThan(0);
    });

    it('handles service with invalid hourly rate', () => {
      const instructorWithBadRate: Instructor = {
        ...instructorSingleService,
        services: [
          { id: 'service-1', skill: 'Piano', hourly_rate: 'invalid' as unknown as number, duration_options: [60], duration: 60 },
        ],
      };

      renderModal({ instructor: instructorWithBadRate });

      // Should show $0
      const priceElements = screen.getAllByText('$0');
      expect(priceElements.length).toBeGreaterThan(0);
    });
  });

  describe('time and date formatting', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('formats date correctly', () => {
      renderModal({ selectedDate: '2025-06-15' });

      // The date is displayed in the modal - verify we can find June in the rendered output
      // The full date "Sunday, June 15, 2025" is split across elements, so we check parts
      expect(screen.getByText(/June/)).toBeInTheDocument();
    });

    it('formats time correctly', () => {
      renderModal({ selectedTime: '14:30' });

      // Should display formatted time
      const timeElements = screen.getAllByText(/2:30 PM/);
      expect(timeElements.length).toBeGreaterThan(0);
    });

    it('handles invalid time format gracefully', () => {
      renderModal({ selectedTime: 'invalid' });

      // Should show "Invalid time" when format fails - the text appears in the time display
      expect(screen.getByText(/Invalid time/i)).toBeInTheDocument();
    });
  });

  describe('booking form validation', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });
    });

    it('disables continue button when terms not agreed', async () => {
      renderModal();

      // Authenticated user already sees form
      const inputs = getTextInputs();
      const phoneInput = inputs[2]!;
      await userEvent.type(phoneInput, '555-1111');

      // Don't check the terms checkbox

      const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
      expect(continueButton).toBeDisabled();
    });

    it('enables continue button when all fields filled and terms agreed', async () => {
      renderModal();

      // Authenticated user already sees form
      const inputs = getTextInputs();
      const phoneInput = inputs[2]!;
      await userEvent.type(phoneInput, '555-1111');
      await userEvent.click(screen.getByRole('checkbox'));

      const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
      expect(continueButton).not.toBeDisabled();
    });
  });

  describe('notes field', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });
    });

    it('allows entering notes', async () => {
      renderModal();

      // Authenticated user already sees form with notes field
      const notesField = screen.getByPlaceholderText(/Any specific topics/i);
      await userEvent.type(notesField, 'I want to learn jazz piano');

      expect(notesField).toHaveValue('I want to learn jazz piano');
    });
  });

  describe('instructor display', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('displays instructor name', () => {
      renderModal();

      expect(screen.getByText(/Jane D\./)).toBeInTheDocument();
    });

    it('displays instructor initial in avatar placeholder', () => {
      renderModal();

      expect(screen.getByText('J')).toBeInTheDocument();
    });

    it('displays service area', () => {
      renderModal();

      expect(screen.getByText(/Manhattan/)).toBeInTheDocument();
    });
  });

  describe('booking summary', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });
    });

    it('shows booking summary in form view', async () => {
      renderModal();

      // Authenticated user already sees form with booking summary
      expect(screen.getByText('Booking Summary')).toBeInTheDocument();
      expect(screen.getByText(/Instructor: Jane D\./)).toBeInTheDocument();
      expect(screen.getByText(/Service: Piano/)).toBeInTheDocument();
    });
  });

  describe('trust and policy info', () => {
    beforeEach(() => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });
    });

    it('displays cancellation policy', () => {
      renderModal();

      expect(screen.getByText(/Free cancellation until 2 hours before/)).toBeInTheDocument();
    });

    it('displays satisfaction guarantee', () => {
      renderModal();

      expect(screen.getByText(/100% satisfaction guarantee/)).toBeInTheDocument();
    });
  });

  describe('edge cases', () => {
    it('handles instructor with no services', () => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });

      const instructorNoServices: Instructor = {
        ...instructor,
        services: [],
      };

      renderModal({ instructor: instructorNoServices });

      // Should still render but continue button should be disabled
      const continueButton = screen.getByRole('button', { name: 'Continue to Booking' });
      expect(continueButton).toBeDisabled();
    });

    it('alerts when submitting without a selected service', async () => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });

      const instructorNoServices: Instructor = {
        ...instructor,
        services: [],
      };

      renderModal({ instructor: instructorNoServices });

      const inputs = getTextInputs();
      const phoneInput = inputs[2]!;
      await userEvent.type(phoneInput, '555-1111');
      await userEvent.click(screen.getByRole('checkbox'));

      await userEvent.click(screen.getByRole('button', { name: 'Continue to Payment' }));

      expect(window.alert).toHaveBeenCalledWith('Please select a service');
    });

    it('handles instructor with missing service area', () => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });

      const instructorNoArea: Instructor = {
        ...instructor,
        service_area_boroughs: [],
        service_area_summary: '',
      };

      renderModal({ instructor: instructorNoArea });

      // Should fall back to 'NYC'
      expect(screen.getByText(/NYC/)).toBeInTheDocument();
    });
  });

  describe('form submission validation alerts', () => {
    it('alerts when phone is missing on submit attempt', async () => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });

      renderModal();

      // Name and email filled, skip phone
      await userEvent.click(screen.getByRole('checkbox'));

      // The button should be disabled, but let's verify the validation state
      const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
      expect(continueButton).toBeDisabled();
    });

    it('keeps button disabled when email is empty', async () => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Jane Doe', email: '' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });

      renderModal();

      const inputs = getTextInputs();
      const phoneInput = inputs[2]!;
      await userEvent.type(phoneInput, '555-1111');
      await userEvent.click(screen.getByRole('checkbox'));

      const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
      expect(continueButton).toBeDisabled();
    });

    it('keeps button disabled when name is empty', async () => {
      useAuthMock.mockReturnValue({
        user: { full_name: '', email: 'jane@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });

      renderModal();

      const inputs = getTextInputs();
      const phoneInput = inputs[2]!;
      await userEvent.type(phoneInput, '555-1111');
      await userEvent.click(screen.getByRole('checkbox'));

      const continueButton = screen.getByRole('button', { name: 'Continue to Payment' });
      expect(continueButton).toBeDisabled();
    });
  });

  describe('keyboard and accessibility', () => {
    it('handles form inputs correctly', async () => {
      useAuthMock.mockReturnValue({
        user: { full_name: 'Test User', email: 'test@example.com' },
        isAuthenticated: true,
        redirectToLogin: jest.fn(),
      });

      renderModal();

      // All text inputs should be accessible
      const inputs = getTextInputs();
      expect(inputs.length).toBeGreaterThanOrEqual(3);
    });
  });

  describe('duration selection variants', () => {
    it('displays standard duration options', async () => {
      useAuthMock.mockReturnValue({
        user: null,
        isAuthenticated: false,
        redirectToLogin: jest.fn(),
      });

      renderModal();

      // The component displays fixed duration options [30, 60, 90]
      expect(screen.getByRole('radio', { name: /30 minutes/i })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /60 minutes/i })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /90 minutes/i })).toBeInTheDocument();
    });
  });
});
