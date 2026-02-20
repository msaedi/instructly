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

  describe('bug-hunting edge cases', () => {
    it('does not crash when studioPins is undefined and offersTravel is true', () => {
      // studioPins defaults to [] via destructuring default, offersTravel alone should show the map
      render(
        <WhereTheyTeach
          offersTravel={true}
          offersAtLocation={true}
          offersOnline={false}
        />
      );

      // Map renders because offersTravel=true makes showMap=true
      expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
      // But effectiveOffersAtLocation is false (no pins), so "At studio" should NOT be in legend
      expect(screen.queryByText(/at studio/i)).not.toBeInTheDocument();
      // Travel legend item should still appear
      expect(screen.getByText(/travels to you/i)).toBeInTheDocument();
    });

    it('renders online-only fallback when offersTravel=false, offersAtLocation=false, offersOnline=true', () => {
      render(
        <WhereTheyTeach
          offersTravel={false}
          offersAtLocation={false}
          offersOnline={true}
        />
      );

      // Should show the "Online lessons only" dashed border fallback, NOT the map
      expect(screen.queryByTestId('coverage-map')).not.toBeInTheDocument();
      expect(screen.getByText(/online lessons only/i)).toBeInTheDocument();
      // Should NOT show the "No lesson options" message
      expect(screen.queryByText(/no lesson options configured yet/i)).not.toBeInTheDocument();
    });

    it('renders map with empty studioPins array when offersAtLocation=true but no actual pins', () => {
      // offersAtLocation=true but studioPins=[] means effectiveOffersAtLocation=false
      // Combined with offersTravel=false and offersOnline=false -> "No lesson options"
      render(
        <WhereTheyTeach
          offersTravel={false}
          offersAtLocation={true}
          offersOnline={false}
          studioPins={[]}
        />
      );

      expect(screen.queryByTestId('coverage-map')).not.toBeInTheDocument();
      expect(screen.getByText(/no lesson options configured yet/i)).toBeInTheDocument();
    });

    it('shows "No lesson options" when all three boolean props are false', () => {
      render(
        <WhereTheyTeach
          offersTravel={false}
          offersAtLocation={false}
          offersOnline={false}
        />
      );

      expect(screen.getByText(/no lesson options configured yet/i)).toBeInTheDocument();
      expect(screen.queryByTestId('coverage-map')).not.toBeInTheDocument();
      expect(screen.queryByText(/online lessons only/i)).not.toBeInTheDocument();
    });

    it('handles offersOnline=true combined with travel showing map with both legend items', () => {
      // When offersTravel=true, showMap=true so the map branch renders, not the online-only branch.
      // The online legend item should appear in the legend alongside "Travels to you".
      render(
        <WhereTheyTeach
          offersTravel={true}
          offersAtLocation={false}
          offersOnline={true}
        />
      );

      expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
      expect(screen.getByText(/travels to you/i)).toBeInTheDocument();
      expect(screen.getByText(/online/i)).toBeInTheDocument();
      // The "Online lessons only" dashed fallback should NOT appear since we're in map mode
      expect(screen.queryByText(/online lessons only/i)).not.toBeInTheDocument();
    });

    it('does not show studio area label when studioLabel is an empty string', () => {
      // Pin has label property but it's empty string — should not render "Approximate studio area: "
      render(
        <WhereTheyTeach
          offersTravel={false}
          offersAtLocation={true}
          offersOnline={false}
          studioPins={[{ lat: 40.7128, lng: -74.006, label: '' }]}
        />
      );

      expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
      // Empty string is falsy, so studioLabel check should prevent rendering
      expect(screen.queryByText(/approximate studio area/i)).not.toBeInTheDocument();
    });

    it('uses only the first pin label for the studio area text, ignoring subsequent pins', () => {
      const pins = [
        { lat: 40.7128, lng: -74.006, label: 'First Studio' },
        { lat: 40.7282, lng: -73.7949, label: 'Second Studio' },
      ];

      render(
        <WhereTheyTeach
          offersTravel={false}
          offersAtLocation={true}
          offersOnline={false}
          studioPins={pins}
        />
      );

      expect(screen.getByText(/approximate studio area: first studio/i)).toBeInTheDocument();
      // Second pin label should NOT appear in the studio area text
      expect(screen.queryByText(/second studio/i)).not.toBeInTheDocument();
    });

    it('renders heading "Where They Teach" regardless of props', () => {
      const { rerender } = render(
        <WhereTheyTeach
          offersTravel={false}
          offersAtLocation={false}
          offersOnline={false}
        />
      );

      expect(screen.getByRole('heading', { name: /where they teach/i })).toBeInTheDocument();

      rerender(
        <WhereTheyTeach
          offersTravel={true}
          offersAtLocation={true}
          offersOnline={true}
          studioPins={[{ lat: 40.7, lng: -74.0 }]}
        />
      );

      expect(screen.getByRole('heading', { name: /where they teach/i })).toBeInTheDocument();
    });

    it('handles coverage=null explicitly without crashing', () => {
      render(
        <WhereTheyTeach
          offersTravel={true}
          offersAtLocation={false}
          offersOnline={false}
          coverage={null}
        />
      );

      // Map should still render — coverage null is valid (no coverage polygon shown)
      expect(screen.getByTestId('coverage-map')).toBeInTheDocument();
    });
  });
});
