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
});
