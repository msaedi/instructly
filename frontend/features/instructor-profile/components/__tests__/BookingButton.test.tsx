import { render, screen, fireEvent } from '@testing-library/react';
import { BookingButton } from '../BookingButton';
import type { InstructorProfile } from '@/types/instructor';

describe('BookingButton', () => {
  const mockInstructorWithServices: InstructorProfile = {
    id: '01K2MAY484FQGFEQVN3VKGYZ58',
    user_id: '01K2MAY484FQGFEQVN3VKGYZ59',
    first_name: 'John',
    last_name: 'Doe',
    email: 'john@example.com',
    role: 'instructor',
    bio: 'Experienced teacher',
    years_experience: 10,
    is_verified: true,
    is_live: true,
    background_check_completed: true,
    profile_image_url: null,
    services: [
      { id: 'svc-1', skill: 'Piano', hourly_rate: 60, duration_options: [30, 60] },
      { id: 'svc-2', skill: 'Guitar', hourly_rate: 45, duration_options: [30, 60] },
      { id: 'svc-3', skill: 'Violin', hourly_rate: 80, duration_options: [60] },
    ],
    favorited_count: 0,
    user: {
      id: '01K2MAY484FQGFEQVN3VKGYZ59',
      first_name: 'John',
      last_name: 'Doe',
      email: 'john@example.com',
      role: 'instructor',
    },
  } as unknown as InstructorProfile;

  const mockInstructorNoServices: InstructorProfile = {
    ...mockInstructorWithServices,
    services: [],
  } as unknown as InstructorProfile;

  const mockInstructorNullServices: InstructorProfile = {
    ...mockInstructorWithServices,
    services: undefined,
  } as unknown as InstructorProfile;

  it('renders book now button with lowest price', () => {
    render(<BookingButton instructor={mockInstructorWithServices} />);

    // Should show the lowest price (45 from Guitar)
    expect(screen.getByTestId('mobile-book-now')).toBeInTheDocument();
    expect(screen.getByText(/book now/i)).toBeInTheDocument();
    expect(screen.getByText(/\$45\/hr/i)).toBeInTheDocument();
  });

  it('calculates lowest price correctly from multiple services', () => {
    render(<BookingButton instructor={mockInstructorWithServices} />);

    // Lowest price should be $45 from Guitar service
    const button = screen.getByTestId('mobile-book-now');
    expect(button.textContent).toContain('$45');
  });

  it('calls onBook callback when clicked', () => {
    const onBook = jest.fn();
    render(<BookingButton instructor={mockInstructorWithServices} onBook={onBook} />);

    fireEvent.click(screen.getByTestId('mobile-book-now'));

    expect(onBook).toHaveBeenCalledTimes(1);
  });

  it('returns null when services array is empty', () => {
    const { container } = render(<BookingButton instructor={mockInstructorNoServices} />);

    expect(container.firstChild).toBeNull();
  });

  it('returns null when services is undefined', () => {
    const { container } = render(<BookingButton instructor={mockInstructorNullServices} />);

    expect(container.firstChild).toBeNull();
  });

  it('applies custom className', () => {
    const { container } = render(
      <BookingButton instructor={mockInstructorWithServices} className="custom-class" />
    );

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveClass('custom-class');
  });

  it('renders with fixed positioning for mobile', () => {
    const { container } = render(<BookingButton instructor={mockInstructorWithServices} />);

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveClass('fixed', 'bottom-0', 'left-0', 'right-0');
  });

  it('handles single service correctly', () => {
    const singleServiceInstructor: InstructorProfile = {
      ...mockInstructorWithServices,
      services: [{ id: 'svc-1', skill: 'Piano', hourly_rate: 75, duration_options: [60] }],
    } as InstructorProfile;

    render(<BookingButton instructor={singleServiceInstructor} />);

    expect(screen.getByText(/\$75\/hr/i)).toBeInTheDocument();
  });

  it('handles service with zero hourly rate', () => {
    const zeroRateInstructor: InstructorProfile = {
      ...mockInstructorWithServices,
      services: [
        { id: 'svc-1', skill: 'Piano', hourly_rate: 0, duration_options: [60] },
        { id: 'svc-2', skill: 'Guitar', hourly_rate: 50, duration_options: [60] },
      ],
    } as InstructorProfile;

    render(<BookingButton instructor={zeroRateInstructor} />);

    // Should show $0/hr as the lowest
    expect(screen.getByText(/\$0\/hr/i)).toBeInTheDocument();
  });

  it('has correct button styling', () => {
    render(<BookingButton instructor={mockInstructorWithServices} />);

    const button = screen.getByTestId('mobile-book-now');
    expect(button).toHaveClass('w-full', 'py-3', 'px-6', 'rounded-lg', 'font-medium');
  });
});
