import { render, screen } from '@testing-library/react';
import { AboutCard } from '../AboutCard';
import type { InstructorProfile } from '@/types/instructor';

// Mock the BGCBadge component
jest.mock('@/components/ui/BGCBadge', () => ({
  BGCBadge: ({ isLive, bgcStatus }: { isLive: boolean; bgcStatus: string | null }) => (
    <span data-testid="bgc-badge" data-live={isLive} data-status={bgcStatus}>
      BGC Badge
    </span>
  ),
}));

describe('AboutCard', () => {
  const baseInstructor: InstructorProfile = {
    id: '01K2MAY484FQGFEQVN3VKGYZ58',
    first_name: 'John',
    last_name: 'Doe',
    email: 'john@example.com',
    role: 'instructor',
    bio: 'I am an experienced piano teacher with a passion for music education.',
    years_experience: 10,
    is_verified: true,
    is_live: true,
    background_check_completed: true,
    profile_image_url: null,
    services: [],
  } as unknown as InstructorProfile;

  it('renders the About card title', () => {
    render(<AboutCard instructor={baseInstructor} />);

    expect(screen.getByText('About')).toBeInTheDocument();
  });

  it('displays years of experience when greater than zero', () => {
    render(<AboutCard instructor={baseInstructor} />);

    expect(screen.getByText('Experience')).toBeInTheDocument();
    expect(screen.getByText('10 years teaching')).toBeInTheDocument();
  });

  it('does not display experience section when years_experience is 0', () => {
    const instructor = { ...baseInstructor, years_experience: 0 };
    render(<AboutCard instructor={instructor} />);

    expect(screen.queryByText('Experience')).not.toBeInTheDocument();
  });

  it('displays languages section', () => {
    render(<AboutCard instructor={baseInstructor} />);

    expect(screen.getByText('Languages')).toBeInTheDocument();
    expect(screen.getByText('English, Spanish')).toBeInTheDocument();
  });

  it('displays education section', () => {
    render(<AboutCard instructor={baseInstructor} />);

    expect(screen.getByText('Education')).toBeInTheDocument();
    expect(screen.getByText('BA Music Education, NYU')).toBeInTheDocument();
  });

  it('displays bio when present', () => {
    render(<AboutCard instructor={baseInstructor} />);

    expect(screen.getByText(baseInstructor.bio as string)).toBeInTheDocument();
  });

  it('does not display bio section when bio is null', () => {
    const instructor = { ...baseInstructor, bio: null } as unknown as InstructorProfile;
    render(<AboutCard instructor={instructor} />);

    expect(screen.queryByText(/I am an experienced/)).not.toBeInTheDocument();
  });

  it('does not display bio section when bio is empty', () => {
    const instructor = { ...baseInstructor, bio: '' };
    render(<AboutCard instructor={instructor} />);

    // Bio section should not have any content
    const bioText = 'I am an experienced piano teacher';
    expect(screen.queryByText(bioText)).not.toBeInTheDocument();
  });

  it('displays Verified badge when is_verified is true', () => {
    render(<AboutCard instructor={baseInstructor} />);

    expect(screen.getByText('Verified')).toBeInTheDocument();
  });

  it('does not display Verified badge when is_verified is false', () => {
    const instructor = { ...baseInstructor, is_verified: false };
    render(<AboutCard instructor={instructor} />);

    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
  });

  it('displays BGC badge when instructor is live', () => {
    render(<AboutCard instructor={baseInstructor} />);

    expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
  });

  it('displays BGC badge when bgc_status is pending', () => {
    const instructor = {
      ...baseInstructor,
      is_live: false,
      bgc_status: 'pending',
    } as InstructorProfile & { bgc_status: string };

    render(<AboutCard instructor={instructor} />);

    expect(screen.getByTestId('bgc-badge')).toBeInTheDocument();
  });

  it('does not display BGC badge when not live and no pending status', () => {
    const instructor = {
      ...baseInstructor,
      is_live: false,
      bgc_status: null,
      background_check_completed: false,
    } as InstructorProfile & { bgc_status: null };

    render(<AboutCard instructor={instructor} />);

    expect(screen.queryByTestId('bgc-badge')).not.toBeInTheDocument();
  });

  it('renders all icons correctly', () => {
    render(<AboutCard instructor={baseInstructor} />);

    // Check that sections are present (icons are rendered with lucide-react)
    expect(screen.getByText('Experience')).toBeInTheDocument();
    expect(screen.getByText('Languages')).toBeInTheDocument();
    expect(screen.getByText('Education')).toBeInTheDocument();
  });

  it('handles instructor with minimal data', () => {
    const minimalInstructor: InstructorProfile = {
      id: '01K2MAY484FQGFEQVN3VKGYZ58',
      first_name: 'Jane',
      last_name: 'Smith',
      email: 'jane@example.com',
      role: 'instructor',
      bio: null,
      years_experience: 0,
      is_verified: false,
      is_live: false,
      background_check_completed: false,
      profile_image_url: null,
      services: [],
    } as unknown as InstructorProfile;

    render(<AboutCard instructor={minimalInstructor} />);

    // Should still render the card without crashing
    expect(screen.getByText('About')).toBeInTheDocument();
    // Should not show experience or verified badge
    expect(screen.queryByText('Experience')).not.toBeInTheDocument();
    expect(screen.queryByText('Verified')).not.toBeInTheDocument();
  });
});
