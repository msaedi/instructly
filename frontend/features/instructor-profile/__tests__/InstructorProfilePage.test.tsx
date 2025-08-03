import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { useInstructorProfile } from '../hooks/useInstructorProfile';
import { InstructorHeader } from '../components/InstructorHeader';

// Mock the hooks
jest.mock('../hooks/useInstructorProfile');
jest.mock('../hooks/useSaveInstructor', () => ({
  useSaveInstructor: () => ({
    isSaved: false,
    toggleSave: jest.fn(),
    isLoading: false,
  }),
}));

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    back: jest.fn(),
  }),
  useParams: () => ({
    id: '1',
  }),
}));

const mockInstructor = {
  id: 1,
  user_id: 1,
  bio: 'Experienced piano teacher with 10 years of experience',
  areas_of_service: ['Upper West Side', 'Manhattan'],
  years_experience: 10,
  user: {
    full_name: 'Sarah Chen',
    email: 'sarah@example.com',
  },
  services: [
    {
      id: 1,
      skill: 'Piano',
      hourly_rate: 75,
      description: 'Piano lessons for all levels',
      duration_minutes: 60,
      is_active: true,
    },
    {
      id: 2,
      skill: 'Music Theory',
      hourly_rate: 65,
      description: 'Comprehensive music theory',
      duration_minutes: 45,
      is_active: true,
    },
  ],
  is_verified: true,
  background_check_completed: true,
};

describe('InstructorProfilePage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('renders instructor header with correct information', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <InstructorHeader instructor={mockInstructor} />
      </QueryClientProvider>
    );

    expect(screen.getByText('Sarah Chen')).toBeInTheDocument();
    expect(screen.getByText('10 years experience')).toBeInTheDocument();
    expect(screen.getByText(/Upper West Side/)).toBeInTheDocument();
  });

  it('displays loading state while fetching data', () => {
    (useInstructorProfile as jest.Mock).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <div>Loading...</div>
      </QueryClientProvider>
    );

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('displays error state when fetch fails', () => {
    (useInstructorProfile as jest.Mock).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Failed to fetch'),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <div>Error loading profile</div>
      </QueryClientProvider>
    );

    expect(screen.getByText('Error loading profile')).toBeInTheDocument();
  });

  it('displays services with correct pricing', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <div>
          {mockInstructor.services.map((service) => (
            <div key={service.id}>
              <span>{service.skill}</span>
              <span>${service.hourly_rate}</span>
            </div>
          ))}
        </div>
      </QueryClientProvider>
    );

    expect(screen.getByText('Piano')).toBeInTheDocument();
    expect(screen.getByText('$75')).toBeInTheDocument();
    expect(screen.getByText('Music Theory')).toBeInTheDocument();
    expect(screen.getByText('$65')).toBeInTheDocument();
  });

  it('shows verification badges when instructor is verified', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <InstructorHeader instructor={mockInstructor} />
      </QueryClientProvider>
    );

    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.getByText('Background Checked')).toBeInTheDocument();
  });
});
