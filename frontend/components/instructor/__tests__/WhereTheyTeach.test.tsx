import React from 'react';
import { render, screen } from '@testing-library/react';
import { WhereTheyTeach } from '../WhereTheyTeach';

jest.mock('next/dynamic', () => () => {
  const MockCoverageMap = ({
    locationPins,
    showCoverage,
  }: {
    locationPins?: unknown[];
    showCoverage?: boolean;
  }) => (
    <div
      data-testid="coverage-map"
      data-pin-count={Array.isArray(locationPins) ? locationPins.length : 0}
      data-show-coverage={showCoverage ? 'true' : 'false'}
    />
  );
  MockCoverageMap.displayName = 'MockCoverageMap';
  return MockCoverageMap;
});

describe('WhereTheyTeach', () => {
  it('renders fallback when no lesson options are configured', () => {
    render(
      <WhereTheyTeach
        offersTravel={false}
        offersAtLocation={false}
        offersOnline={false}
      />
    );

    expect(screen.getByText(/no lesson options configured yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId('coverage-map')).not.toBeInTheDocument();
  });

  it('renders online-only messaging when only online is offered', () => {
    render(
      <WhereTheyTeach
        offersTravel={false}
        offersAtLocation={false}
        offersOnline={true}
      />
    );

    expect(screen.getByText(/online lessons only/i)).toBeInTheDocument();
    expect(screen.queryByTestId('coverage-map')).not.toBeInTheDocument();
  });

  it('renders map and legend for travel and studio options', () => {
    render(
      <WhereTheyTeach
        offersTravel={true}
        offersAtLocation={true}
        offersOnline={false}
        coverage={{ type: 'FeatureCollection', features: [] }}
        studioPins={[{ lat: 40.7128, lng: -74.0060, label: 'Lower East Side' }]}
      />
    );

    expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
    expect(screen.getByText(/travels to you/i)).toBeInTheDocument();
    expect(screen.getByText(/at studio/i)).toBeInTheDocument();
    expect(screen.queryByText(/online/i)).not.toBeInTheDocument();
    expect(screen.getByText(/approximate studio area/i)).toBeInTheDocument();
  });

  it('includes dark mode classes on the container', () => {
    const { container } = render(
      <WhereTheyTeach
        offersTravel={true}
        offersAtLocation={false}
        offersOnline={false}
      />
    );

    const section = container.querySelector('section');
    expect(section).toBeInTheDocument();
    expect(section).toHaveClass('dark:border-gray-700');
    expect(section).toHaveClass('dark:bg-gray-900');
  });

  it('renders the InstructorCoverageMap with coverage data when offersTravel is true', () => {
    const coverage = {
      type: 'FeatureCollection' as const,
      features: [
        {
          type: 'Feature' as const,
          geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] },
          properties: { name: 'Test Zone' },
        },
      ],
    };

    render(
      <WhereTheyTeach
        offersTravel={true}
        offersAtLocation={false}
        offersOnline={true}
        coverage={coverage}
      />
    );

    const map = screen.getByTestId('coverage-map');
    expect(map).toBeInTheDocument();
    expect(map).toHaveAttribute('data-show-coverage', 'true');
    // Legend should include both travel and online
    expect(screen.getByText(/travels to you/i)).toBeInTheDocument();
    expect(screen.getByText(/online/i)).toBeInTheDocument();
  });

  it('renders map with studio pins and displays approximate studio area', () => {
    const pins = [
      { lat: 40.7128, lng: -74.006, label: 'Midtown Manhattan' },
      { lat: 40.7282, lng: -73.7949, label: 'Queens Studio' },
    ];

    render(
      <WhereTheyTeach
        offersTravel={false}
        offersAtLocation={true}
        offersOnline={false}
        studioPins={pins}
      />
    );

    const map = screen.getByTestId('coverage-map');
    expect(map).toBeInTheDocument();
    expect(map).toHaveAttribute('data-pin-count', '2');
    expect(map).toHaveAttribute('data-show-coverage', 'false');
    expect(screen.getByText(/at studio/i)).toBeInTheDocument();
    expect(screen.getByText(/approximate studio area: midtown manhattan/i)).toBeInTheDocument();
  });

  it('does not render studio option when offersAtLocation is true but no pins provided', () => {
    render(
      <WhereTheyTeach
        offersTravel={false}
        offersAtLocation={true}
        offersOnline={true}
        studioPins={[]}
      />
    );

    // Without studio pins, effectiveOffersAtLocation is false, so map should not show
    expect(screen.queryByTestId('coverage-map')).not.toBeInTheDocument();
    // Should show online-only since that is the only remaining option
    expect(screen.getByText(/online lessons only/i)).toBeInTheDocument();
  });

  it('does not show studio area label when the first pin has no label', () => {
    render(
      <WhereTheyTeach
        offersTravel={false}
        offersAtLocation={true}
        offersOnline={false}
        studioPins={[{ lat: 40.7128, lng: -74.006 }]}
      />
    );

    expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
    expect(screen.queryByText(/approximate studio area/i)).not.toBeInTheDocument();
  });

  it('renders all three legend items when all options are offered with studio pins', () => {
    render(
      <WhereTheyTeach
        offersTravel={true}
        offersAtLocation={true}
        offersOnline={true}
        coverage={{ type: 'FeatureCollection', features: [] }}
        studioPins={[{ lat: 40.7128, lng: -74.006, label: 'Downtown' }]}
      />
    );

    expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
    expect(screen.getByText(/travels to you/i)).toBeInTheDocument();
    expect(screen.getByText(/at studio/i)).toBeInTheDocument();
    expect(screen.getByText(/online/i)).toBeInTheDocument();
    expect(screen.getByText(/approximate studio area: downtown/i)).toBeInTheDocument();
  });

  it('renders map with travel only (no studio pins, no online)', () => {
    render(
      <WhereTheyTeach
        offersTravel={true}
        offersAtLocation={false}
        offersOnline={false}
        coverage={{ type: 'FeatureCollection', features: [] }}
      />
    );

    expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
    expect(screen.getByText(/travels to you/i)).toBeInTheDocument();
    expect(screen.queryByText(/at studio/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/online lessons only/i)).not.toBeInTheDocument();
  });

  it('passes null coverage when coverage prop is undefined', () => {
    render(
      <WhereTheyTeach
        offersTravel={true}
        offersAtLocation={false}
        offersOnline={false}
      />
    );

    // Map should render (offersTravel is true which makes showMap true)
    expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
  });

  it('does not show map when offersAtLocation is true but studioPins is undefined (defaults to empty)', () => {
    render(
      <WhereTheyTeach
        offersTravel={false}
        offersAtLocation={true}
        offersOnline={false}
      />
    );

    // studioPins defaults to [] so effectiveOffersAtLocation = false
    // showMap = false, hasLessonOptions = false
    expect(screen.queryByTestId('coverage-map')).not.toBeInTheDocument();
    expect(screen.getByText(/no lesson options configured yet/i)).toBeInTheDocument();
  });
});
