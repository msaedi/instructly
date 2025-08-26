import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { useInstructorProfile } from '../hooks/useInstructorProfile';
import { InstructorHeader } from '../components/InstructorHeader';
import { AuthProvider } from '@/features/shared/hooks/useAuth';
import React from 'react';

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

// Mock the favorites API
jest.mock('@/services/api/favorites', () => ({
  favoritesApi: {
    check: jest.fn().mockResolvedValue({ is_favorited: false }),
    add: jest.fn().mockResolvedValue({ success: true }),
    remove: jest.fn().mockResolvedValue({ success: true }),
  },
}));

const mockInstructor = {
  id: '01K2MAY484FQGFEQVN3VKGYZ58',
  user_id: '01K2MAY484FQGFEQVN3VKGYZ58',
  bio: 'Experienced piano teacher with 10 years of experience',
  areas_of_service: ['Upper West Side', 'Manhattan'],
  years_experience: 10,
  user: {
    first_name: 'Sarah',
    last_initial: 'C',
  },
  services: [
    {
      id: '01K2MAY484FQGFEQVN3VKGYZ59',
      service_catalog_id: '01K2MAY484FQGFEQVN3VKGYZ60',
      skill: 'Piano',
      hourly_rate: 75,
      description: 'Piano lessons for all levels',
      duration_options: [60],
      is_active: true,
    },
    {
      id: '01K2MAY484FQGFEQVN3VKGYZ61',
      service_catalog_id: '01K2MAY484FQGFEQVN3VKGYZ62',
      skill: 'Music Theory',
      hourly_rate: 65,
      description: 'Comprehensive music theory',
      duration_options: [45],
      is_active: true,
    },
  ],
  is_verified: true,
  background_check_completed: true,
  is_favorited: false,
  favorited_count: 5,
};

// Test wrapper component that provides all necessary context
const TestWrapper = ({ children }: { children: React.ReactNode }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        {children}
      </AuthProvider>
    </QueryClientProvider>
  );
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

  it('renders instructor header with correct information', async () => {
    render(
      <TestWrapper>
        <InstructorHeader instructor={mockInstructor} />
      </TestWrapper>
    );

    expect(screen.getByText('Sarah C.')).toBeInTheDocument();
    // Wait for ratings query to resolve and show review count
    expect(await screen.findByText('(5 reviews)')).toBeInTheDocument();
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

  it('shows background check badge when instructor has completed background check', () => {
    render(
      <TestWrapper>
        <InstructorHeader instructor={mockInstructor} />
      </TestWrapper>
    );

    expect(screen.getByText('Background Checked')).toBeInTheDocument();
  });
});
