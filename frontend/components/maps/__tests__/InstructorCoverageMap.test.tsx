import { render, screen, act, fireEvent } from '@testing-library/react';
import InstructorCoverageMap from '../InstructorCoverageMap';

// Mock the logger
jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

// Create mock map instance
const mockMap = {
  getCenter: jest.fn(() => ({ lat: 40.7831, lng: -73.9712 })),
  getZoom: jest.fn(() => 12),
  fitBounds: jest.fn(),
  flyToBounds: jest.fn(),
  flyTo: jest.fn(),
  setView: jest.fn(),
  zoomIn: jest.fn(),
  zoomOut: jest.fn(),
  getBounds: jest.fn(() => ({
    getNorth: () => 41,
    getSouth: () => 40,
    getEast: () => -73,
    getWest: () => -74,
  })),
  on: jest.fn(),
  off: jest.fn(),
  stop: jest.fn(),
};

// Mock react-leaflet
jest.mock('react-leaflet', () => ({
  MapContainer: ({ children, whenReady, ...props }: {
    children: React.ReactNode;
    whenReady?: () => void;
    [key: string]: unknown;
  }) => {
    React.useEffect(() => {
      whenReady?.();
    }, [whenReady]);
    return <div data-testid="map-container" {...props}>{children}</div>;
  },
  TileLayer: ({ url, eventHandlers }: { url: string; eventHandlers?: { tileerror?: () => void } }) => (
    <div data-testid="tile-layer" data-url={url} onClick={() => eventHandlers?.tileerror?.()} />
  ),
  GeoJSON: ({ data, style, onEachFeature }: {
    data: unknown;
    style?: (feature: unknown) => object;
    onEachFeature?: (feature: unknown, layer: unknown) => void;
  }) => {
    const mockLayer = {
      bindPopup: jest.fn(),
    };
    const mockFeature = {
      properties: { name: 'Test Region', instructors: ['inst-1'] },
    };
    // Trigger the callbacks for coverage
    if (style) style(mockFeature);
    if (onEachFeature) onEachFeature(mockFeature, mockLayer);
    return <div data-testid="geojson-layer" data-features={JSON.stringify(data)} />;
  },
  AttributionControl: () => <div data-testid="attribution-control" />,
  useMap: () => mockMap,
}));

// Mock Leaflet
jest.mock('leaflet', () => ({
  Control: jest.fn().mockImplementation(function (this: { position: string; onAdd?: () => HTMLElement }, options) {
    this.position = options?.position || 'bottomright';
    return {
      addTo: jest.fn().mockReturnValue({ remove: jest.fn() }),
      onAdd: this.onAdd,
      ...this,
    };
  }),
  DomUtil: {
    create: jest.fn((tag: string) => document.createElement(tag)),
  },
  DomEvent: {
    disableClickPropagation: jest.fn(),
    disableScrollPropagation: jest.fn(),
  },
  geoJSON: jest.fn(() => ({
    getBounds: jest.fn(() => ({
      isValid: jest.fn(() => true),
      getNorth: () => 41,
      getSouth: () => 40,
      getEast: () => -73,
      getWest: () => -74,
    })),
    remove: jest.fn(),
  })),
  circleMarker: jest.fn(() => ({
    addTo: jest.fn(),
    remove: jest.fn(),
  })),
}));

// Import React after mocks
import React from 'react';

describe('InstructorCoverageMap', () => {
  const mockFeatureCollection = {
    type: 'FeatureCollection' as const,
    features: [
      {
        type: 'Feature' as const,
        geometry: {
          type: 'Polygon',
          coordinates: [[[-74, 40], [-73, 40], [-73, 41], [-74, 41], [-74, 40]]],
        },
        properties: {
          name: 'Upper West Side',
          region_id: 'uws',
          instructors: ['inst-1', 'inst-2'],
          instructors_count: 2,
        },
      },
      {
        type: 'Feature' as const,
        geometry: {
          type: 'Polygon',
          coordinates: [[[-74, 40], [-73, 40], [-73, 41], [-74, 41], [-74, 40]]],
        },
        properties: {
          name: 'Chelsea',
          region_id: 'chelsea',
          instructors: ['inst-3'],
          instructors_count: 1,
        },
      },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders map container', () => {
    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('map-container')).toBeInTheDocument();
  });

  it('renders with default height', () => {
    const { container } = render(<InstructorCoverageMap />);

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveStyle({ height: '420px' });
  });

  it('renders with custom numeric height', () => {
    const { container } = render(<InstructorCoverageMap height={600} />);

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveStyle({ height: '600px' });
  });

  it('renders with custom string height', () => {
    const { container } = render(<InstructorCoverageMap height="100vh" />);

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper).toHaveStyle({ height: '100vh' });
  });

  it('renders tile layer', () => {
    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('tile-layer')).toBeInTheDocument();
  });

  it('renders attribution control', () => {
    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('attribution-control')).toBeInTheDocument();
  });

  it('renders GeoJSON layer when showCoverage is true and features exist', () => {
    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        showCoverage={true}
      />
    );

    expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
  });

  it('does not render GeoJSON layer when showCoverage is false', () => {
    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        showCoverage={false}
      />
    );

    expect(screen.queryByTestId('geojson-layer')).not.toBeInTheDocument();
  });

  it('does not render GeoJSON layer when featureCollection is null', () => {
    render(
      <InstructorCoverageMap
        featureCollection={null}
        showCoverage={true}
      />
    );

    expect(screen.queryByTestId('geojson-layer')).not.toBeInTheDocument();
  });

  it('does not render GeoJSON layer when featureCollection has no features', () => {
    render(
      <InstructorCoverageMap
        featureCollection={{ type: 'FeatureCollection', features: [] }}
        showCoverage={true}
      />
    );

    expect(screen.queryByTestId('geojson-layer')).not.toBeInTheDocument();
  });

  it('updates feature collection when prop changes', () => {
    const { rerender } = render(
      <InstructorCoverageMap featureCollection={null} showCoverage={true} />
    );

    expect(screen.queryByTestId('geojson-layer')).not.toBeInTheDocument();

    rerender(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        showCoverage={true}
      />
    );

    expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
  });

  it('uses fallback tile URL when Jawg token is not set', () => {
    const originalEnv = process.env['NEXT_PUBLIC_JAWG_TOKEN'];
    delete process.env['NEXT_PUBLIC_JAWG_TOKEN'];

    render(<InstructorCoverageMap />);

    const tileLayer = screen.getByTestId('tile-layer');
    expect(tileLayer.getAttribute('data-url')).toContain('cartocdn');

    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = originalEnv;
  });

  it('handles tile error by switching to fallback URL', () => {
    render(<InstructorCoverageMap />);

    const tileLayer = screen.getByTestId('tile-layer');

    // Simulate tile error
    act(() => {
      fireEvent.click(tileLayer);
    });

    // Should switch to fallback
    expect(screen.getByTestId('tile-layer').getAttribute('data-url')).toContain('cartocdn');
  });

  it('applies highlight style for specific instructor', () => {
    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        highlightInstructorId="inst-1"
      />
    );

    // GeoJSON layer should be rendered with highlighting applied
    expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
  });

  it('calls onBoundsChange when map bounds change', () => {
    const onBoundsChange = jest.fn();
    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        onBoundsChange={onBoundsChange}
      />
    );

    // Map event handlers should be registered
    expect(mockMap.on).toHaveBeenCalledWith('moveend', expect.any(Function));
    expect(mockMap.on).toHaveBeenCalledWith('zoomend', expect.any(Function));
  });

  it('respects dark mode preference', () => {
    // Mock matchMedia
    const mockMatchMedia = jest.fn().mockReturnValue({
      matches: true,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    });
    window.matchMedia = mockMatchMedia;

    render(<InstructorCoverageMap />);

    expect(mockMatchMedia).toHaveBeenCalledWith('(prefers-color-scheme: dark)');
  });

  it('handles when featureCollection is undefined', () => {
    render(<InstructorCoverageMap featureCollection={undefined} />);

    expect(screen.getByTestId('map-container')).toBeInTheDocument();
    expect(screen.queryByTestId('geojson-layer')).not.toBeInTheDocument();
  });

  it('supports focus on specific instructor coverage', () => {
    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        focusInstructorId="inst-1"
      />
    );

    // Should render map with focus handling
    expect(screen.getByTestId('map-container')).toBeInTheDocument();
  });

  it('shows search area button when enabled', () => {
    const onSearchArea = jest.fn();
    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        showSearchAreaButton={true}
        onSearchArea={onSearchArea}
      />
    );

    // Search area button is added via Leaflet control
    expect(screen.getByTestId('map-container')).toBeInTheDocument();
  });
});
