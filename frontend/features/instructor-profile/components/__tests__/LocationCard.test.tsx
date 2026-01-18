import { render, screen } from '@testing-library/react';
import { LocationCard } from '../LocationCard';
import type { InstructorProfile } from '@/types/instructor';
import { getServiceAreaDisplay } from '@/lib/profileServiceAreas';

// Mock the service area helper
jest.mock('@/lib/profileServiceAreas', () => ({
  getServiceAreaDisplay: jest.fn(),
}));

const getServiceAreaDisplayMock = getServiceAreaDisplay as jest.Mock;

describe('LocationCard', () => {
  const baseInstructor: InstructorProfile = {
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
    services: [],
    favorited_count: 0,
    user: {
      id: '01K2MAY484FQGFEQVN3VKGYZ59',
      first_name: 'John',
      last_name: 'Doe',
      email: 'john@example.com',
      role: 'instructor',
    },
  } as unknown as InstructorProfile;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the Location card title', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan, Brooklyn');
    render(<LocationCard instructor={baseInstructor} />);

    expect(screen.getByText('Location')).toBeInTheDocument();
  });

  it('displays service areas when available', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan, Brooklyn');
    render(<LocationCard instructor={baseInstructor} />);

    expect(screen.getByText('Service Areas')).toBeInTheDocument();
    expect(screen.getByText('Manhattan, Brooklyn')).toBeInTheDocument();
  });

  it('does not display service areas section when display is empty', () => {
    getServiceAreaDisplayMock.mockReturnValue('');
    render(<LocationCard instructor={baseInstructor} />);

    expect(screen.queryByText('Service Areas')).not.toBeInTheDocument();
  });

  it('does not display service areas section when display is null', () => {
    getServiceAreaDisplayMock.mockReturnValue(null);
    render(<LocationCard instructor={baseInstructor} />);

    expect(screen.queryByText('Service Areas')).not.toBeInTheDocument();
  });

  it('displays lesson locations section', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan');
    render(<LocationCard instructor={baseInstructor} />);

    expect(screen.getByText('Lesson Locations')).toBeInTheDocument();
    expect(screen.getByText("Instructor's Home")).toBeInTheDocument();
    expect(screen.getByText("Student's Home")).toBeInTheDocument();
    expect(screen.getByText('Online Lessons')).toBeInTheDocument();
  });

  it('displays travel radius section', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan');
    render(<LocationCard instructor={baseInstructor} />);

    expect(screen.getByText('Travel Radius')).toBeInTheDocument();
    expect(screen.getByText('Up to 5 miles from home base')).toBeInTheDocument();
  });

  it('displays map preview placeholder', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan');
    render(<LocationCard instructor={baseInstructor} />);

    expect(screen.getByText('Map preview coming soon')).toBeInTheDocument();
  });

  it('calls getServiceAreaDisplay with instructor', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan');
    render(<LocationCard instructor={baseInstructor} />);

    expect(getServiceAreaDisplayMock).toHaveBeenCalledWith(baseInstructor);
  });

  it('handles multiline service area display', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan\nBrooklyn\nQueens');
    render(<LocationCard instructor={baseInstructor} />);

    // Text with newlines renders as whitespace-pre-line, check for content presence
    expect(screen.getByText(/Manhattan/)).toBeInTheDocument();
  });

  it('renders all three lesson location types', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan');
    render(<LocationCard instructor={baseInstructor} />);

    const lessonLocations = [
      "Instructor's Home",
      "Student's Home",
      'Online Lessons',
    ];

    lessonLocations.forEach((location) => {
      expect(screen.getByText(location)).toBeInTheDocument();
    });
  });

  it('renders with proper card structure', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan');
    const { container } = render(<LocationCard instructor={baseInstructor} />);

    // Should have Card as root element
    expect(container.querySelector('[class*="card"]')).toBeInTheDocument();
  });

  it('renders icons for each section', () => {
    getServiceAreaDisplayMock.mockReturnValue('Manhattan');
    render(<LocationCard instructor={baseInstructor} />);

    // Verify sections with icons exist
    expect(screen.getByText('Service Areas')).toBeInTheDocument();
    expect(screen.getByText('Lesson Locations')).toBeInTheDocument();
    expect(screen.getByText('Travel Radius')).toBeInTheDocument();
  });
});
