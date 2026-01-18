import { render, screen } from '@testing-library/react';
import { InstructorInfo } from '../InstructorInfo';
import type { InstructorProfile } from '@/types/instructor';
import { getServiceAreaBoroughs, getServiceAreaDisplay } from '@/lib/profileServiceAreas';

// Mock the service area helpers
jest.mock('@/lib/profileServiceAreas', () => ({
  getServiceAreaBoroughs: jest.fn(),
  getServiceAreaDisplay: jest.fn(),
}));

const getServiceAreaBoroughsMock = getServiceAreaBoroughs as jest.Mock;
const getServiceAreaDisplayMock = getServiceAreaDisplay as jest.Mock;

describe('InstructorInfo', () => {
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
    getServiceAreaBoroughsMock.mockReturnValue(['Manhattan', 'Brooklyn']);
    getServiceAreaDisplayMock.mockReturnValue('Manhattan, Brooklyn');
  });

  it('renders all three info cards', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(screen.getByText('Location')).toBeInTheDocument();
    expect(screen.getByText('Qualifications')).toBeInTheDocument();
    expect(screen.getByText('Policies')).toBeInTheDocument();
  });

  it('displays service area when available', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(screen.getByText('Manhattan, Brooklyn')).toBeInTheDocument();
    expect(screen.getByText('Available for in-person lessons')).toBeInTheDocument();
  });

  it('displays "Location not specified" when no service areas', () => {
    getServiceAreaBoroughsMock.mockReturnValue([]);
    getServiceAreaDisplayMock.mockReturnValue(null);
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(screen.getByText('Location not specified')).toBeInTheDocument();
  });

  it('displays years of experience in qualifications', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(screen.getByText('10 years teaching experience')).toBeInTheDocument();
  });

  it('does not show experience when years_experience is 0', () => {
    const instructor = { ...baseInstructor, years_experience: 0 };
    render(<InstructorInfo instructor={instructor} />);

    expect(screen.queryByText(/years teaching experience/)).not.toBeInTheDocument();
  });

  it('displays verified badge when is_verified is true', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(screen.getByText('Identity verified')).toBeInTheDocument();
  });

  it('does not show verified badge when is_verified is false', () => {
    const instructor = { ...baseInstructor, is_verified: false };
    render(<InstructorInfo instructor={instructor} />);

    expect(screen.queryByText('Identity verified')).not.toBeInTheDocument();
  });

  it('displays background check verified when completed', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(screen.getByText('Background check verified')).toBeInTheDocument();
  });

  it('does not show background check when not completed', () => {
    const instructor = { ...baseInstructor, background_check_completed: false };
    render(<InstructorInfo instructor={instructor} />);

    expect(screen.queryByText('Background check verified')).not.toBeInTheDocument();
  });

  it('displays all policy items', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(screen.getByText('Free cancellation up to 24hrs before lesson')).toBeInTheDocument();
    expect(screen.getByText('First lesson satisfaction guarantee')).toBeInTheDocument();
    expect(screen.getByText('In-person lessons only')).toBeInTheDocument();
  });

  it('calls service area helpers with instructor', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    expect(getServiceAreaBoroughsMock).toHaveBeenCalledWith(baseInstructor);
    expect(getServiceAreaDisplayMock).toHaveBeenCalledWith(baseInstructor);
  });

  it('renders instructor with all qualifications', () => {
    render(<InstructorInfo instructor={baseInstructor} />);

    // Should show all 3 qualification items
    const qualificationItems = screen.getAllByText('•');
    // 3 qualifications + 3 policies = 6 total bullets
    expect(qualificationItems.length).toBeGreaterThanOrEqual(6);
  });

  it('renders instructor with no qualifications', () => {
    const minimalInstructor = {
      ...baseInstructor,
      years_experience: 0,
      is_verified: false,
      background_check_completed: false,
    };
    render(<InstructorInfo instructor={minimalInstructor} />);

    // Qualifications section should still render but be mostly empty
    expect(screen.getByText('Qualifications')).toBeInTheDocument();
    expect(screen.queryByText('Identity verified')).not.toBeInTheDocument();
    expect(screen.queryByText('Background check verified')).not.toBeInTheDocument();
  });

  it('uses fallback for service area display', () => {
    getServiceAreaBoroughsMock.mockReturnValue([]);
    getServiceAreaDisplayMock.mockReturnValue(null);
    render(<InstructorInfo instructor={baseInstructor} />);

    // Should show default fallback text
    expect(screen.getByText('Location not specified')).toBeInTheDocument();
  });
});
