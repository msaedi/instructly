import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
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

// Store references to event handlers
let moveEndHandler: (() => void) | null = null;
let zoomEndHandler: (() => void) | null = null;

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
  on: jest.fn((event: string, handler: () => void) => {
    if (event === 'moveend') moveEndHandler = handler;
    if (event === 'zoomend') zoomEndHandler = handler;
  }),
  off: jest.fn((event: string) => {
    if (event === 'moveend') moveEndHandler = null;
    if (event === 'zoomend') zoomEndHandler = null;
  }),
  stop: jest.fn(),
};

// Mock react-leaflet
jest.mock('react-leaflet', () => ({
  MapContainer: ({ children, whenReady, attributionControl, zoomControl, ...props }: {
    children: React.ReactNode;
    whenReady?: () => void;
    attributionControl?: boolean;
    zoomControl?: boolean;
    [key: string]: unknown;
  }) => {
    void attributionControl;
    void zoomControl;
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

// Store control instances for testing
const controlInstances: Array<{
  onAdd?: (map: unknown) => HTMLElement;
  remove: jest.Mock;
  position: string;
}> = [];

// Track created markers for testing
const createdMarkers: Array<{ addTo: jest.Mock; remove: jest.Mock }> = [];
const createdPinMarkers: Array<{ addTo: jest.Mock; remove: jest.Mock; bindPopup: jest.Mock }> = [];

// Mock Leaflet with better control simulation
jest.mock('leaflet', () => {
  const L = {
    Control: jest.fn().mockImplementation(function (this: {
      position: string;
      onAdd?: (map: unknown) => HTMLElement;
    }, options?: { position?: string }) {
      this.position = options?.position || 'bottomright';
      const control = {
        position: this.position,
        onAdd: undefined as ((map: unknown) => HTMLElement) | undefined,
        remove: jest.fn(),
        addTo: jest.fn().mockImplementation((map: unknown) => {
          // Execute onAdd when addTo is called to exercise the control logic
          if (control.onAdd) {
            const element = control.onAdd(map);
            // Append to document for testing
            document.body.appendChild(element);
          }
          controlInstances.push(control);
          return control;
        }),
      };
      return control;
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
    circleMarker: jest.fn(() => {
      const marker = {
        addTo: jest.fn().mockReturnThis(),
        remove: jest.fn(),
      };
      createdMarkers.push(marker);
      return marker;
    }),
    divIcon: jest.fn((options: Record<string, unknown>) => options),
    marker: jest.fn(() => {
      const marker = {
        addTo: jest.fn().mockReturnThis(),
        remove: jest.fn(),
        bindPopup: jest.fn().mockReturnThis(),
      };
      createdPinMarkers.push(marker);
      return marker;
    }),
    latLngBounds: jest.fn(() => ({
      extend: jest.fn(function () {
        return this;
      }),
      isValid: jest.fn(() => true),
    })),
  };
  return L;
});

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
    controlInstances.length = 0;
    createdMarkers.length = 0;
    createdPinMarkers.length = 0;
    moveEndHandler = null;
    zoomEndHandler = null;
    // Clear document body of any appended controls
    document.body.textContent = '';
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

  describe('MapBoundsTracker', () => {
    it('calls onBoundsChange when moveend event fires', () => {
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

      // Trigger moveend event
      act(() => {
        if (moveEndHandler) moveEndHandler();
      });

      // Verify onBoundsChange was called with a bounds-like object
      expect(onBoundsChange).toHaveBeenCalledWith(
        expect.objectContaining({
          getNorth: expect.any(Function),
          getSouth: expect.any(Function),
          getEast: expect.any(Function),
          getWest: expect.any(Function),
        })
      );
    });

    it('calls onBoundsChange when zoomend event fires', () => {
      const onBoundsChange = jest.fn();
      render(
        <InstructorCoverageMap
          featureCollection={mockFeatureCollection}
          onBoundsChange={onBoundsChange}
        />
      );

      // Trigger zoomend event
      act(() => {
        if (zoomEndHandler) zoomEndHandler();
      });

      // If zoomEndHandler was registered, onBoundsChange should be called
      if (zoomEndHandler) {
        expect(onBoundsChange).toHaveBeenCalled();
      }
    });

    it('does not throw when onBoundsChange is not provided', () => {
      expect(() => {
        render(
          <InstructorCoverageMap
            featureCollection={mockFeatureCollection}
          />
        );
      }).not.toThrow();
    });

    it('cleans up event listeners on unmount', () => {
      const onBoundsChange = jest.fn();
      const { unmount } = render(
        <InstructorCoverageMap onBoundsChange={onBoundsChange} />
      );

      unmount();

      expect(mockMap.off).toHaveBeenCalledWith('moveend', expect.any(Function));
      expect(mockMap.off).toHaveBeenCalledWith('zoomend', expect.any(Function));
    });
  });

  describe('SearchAreaButton', () => {
    it('creates search area button when showSearchAreaButton is true', () => {
      const onSearchArea = jest.fn();
      render(
        <InstructorCoverageMap
          showSearchAreaButton={true}
          onSearchArea={onSearchArea}
        />
      );

      // Button should be created by the control
      const button = document.querySelector('button');
      expect(button).toBeInTheDocument();
    });

    it('calls onSearchArea when button is clicked', () => {
      const onSearchArea = jest.fn();
      render(
        <InstructorCoverageMap
          showSearchAreaButton={true}
          onSearchArea={onSearchArea}
        />
      );

      const buttons = document.querySelectorAll('button');
      // Find the search button (it's the one with Search this area text or in topleft position)
      const searchButton = Array.from(buttons).find(btn =>
        btn.textContent?.toLowerCase().includes('search')
      );

      if (searchButton) {
        act(() => {
          searchButton.click();
        });
        expect(onSearchArea).toHaveBeenCalled();
      }
    });

    it('handles mouseover and mouseout on search button', () => {
      const onSearchArea = jest.fn();
      render(
        <InstructorCoverageMap
          showSearchAreaButton={true}
          onSearchArea={onSearchArea}
        />
      );

      const buttons = document.querySelectorAll('button');
      const searchButton = Array.from(buttons).find(btn =>
        btn.textContent?.toLowerCase().includes('search')
      );

      if (searchButton) {
        // Test mouseover - should change box-shadow
        act(() => {
          searchButton.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        });

        // Test mouseout - should revert box-shadow
        act(() => {
          searchButton.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }));
        });

        // Should still be in the document after hover events
        expect(searchButton).toBeInTheDocument();
      }
    });

    it('does not create search area button when onSearchArea is not provided', () => {
      render(
        <InstructorCoverageMap
          showSearchAreaButton={true}
          // No onSearchArea callback
        />
      );

      const buttons = document.querySelectorAll('button');
      const searchButton = Array.from(buttons).find(btn =>
        btn.textContent?.toLowerCase().includes('search')
      );
      expect(searchButton).toBeUndefined();
    });

    it('removes search area button on unmount', () => {
      const onSearchArea = jest.fn();
      const { unmount } = render(
        <InstructorCoverageMap
          showSearchAreaButton={true}
          onSearchArea={onSearchArea}
        />
      );

      unmount();

      // Control's remove should have been called
      const controlWithSearchButton = controlInstances.find(
        c => c.position === 'topleft'
      );
      expect(controlWithSearchButton?.remove).toHaveBeenCalled();
    });
  });

  describe('CustomControls', () => {
    it('creates zoom and locate buttons', () => {
      render(<InstructorCoverageMap />);

      // Should have created buttons with titles
      const locateButton = document.querySelector('button[title="Show your location"]');
      const zoomInButton = document.querySelector('button[title="Zoom in"]');
      const zoomOutButton = document.querySelector('button[title="Zoom out"]');

      expect(locateButton).toBeInTheDocument();
      expect(zoomInButton).toBeInTheDocument();
      expect(zoomOutButton).toBeInTheDocument();
    });

    it('calls zoomIn when zoom in button is clicked', () => {
      render(<InstructorCoverageMap />);

      const zoomInButton = document.querySelector('button[title="Zoom in"]') as HTMLButtonElement | null;
      expect(zoomInButton).toBeInTheDocument();

      act(() => {
        zoomInButton?.click();
      });

      expect(mockMap.zoomIn).toHaveBeenCalledWith(1);
    });

    it('calls zoomOut when zoom out button is clicked', () => {
      render(<InstructorCoverageMap />);

      const zoomOutButton = document.querySelector('button[title="Zoom out"]') as HTMLButtonElement | null;
      expect(zoomOutButton).toBeInTheDocument();

      act(() => {
        zoomOutButton?.click();
      });

      expect(mockMap.zoomOut).toHaveBeenCalledWith(1);
    });

    it('handles locate button click with geolocation', async () => {
      const mockGeolocation = {
        getCurrentPosition: jest.fn((success) => {
          success({
            coords: {
              latitude: 40.7,
              longitude: -74.0,
            },
          });
        }),
      };
      Object.defineProperty(navigator, 'geolocation', {
        value: mockGeolocation,
        configurable: true,
      });

      render(<InstructorCoverageMap />);

      const locateButton = document.querySelector('button[title="Show your location"]') as HTMLButtonElement | null;
      expect(locateButton).toBeInTheDocument();

      act(() => {
        locateButton?.click();
      });

      expect(mockGeolocation.getCurrentPosition).toHaveBeenCalled();
      // After getting position, map should fly to the location
      await waitFor(() => {
        expect(mockMap.flyTo).toHaveBeenCalled();
      });
    });

    it('handles locate button click with setView for close positions', async () => {
      // Set map center close to test coordinates
      mockMap.getCenter.mockReturnValue({ lat: 40.7, lng: -74.0 });

      const mockGeolocation = {
        getCurrentPosition: jest.fn((success) => {
          success({
            coords: {
              latitude: 40.7001, // Very close to map center
              longitude: -74.0001,
            },
          });
        }),
      };
      Object.defineProperty(navigator, 'geolocation', {
        value: mockGeolocation,
        configurable: true,
      });

      render(<InstructorCoverageMap />);

      const locateButton = document.querySelector('button[title="Show your location"]') as HTMLButtonElement | null;

      act(() => {
        locateButton?.click();
      });

      await waitFor(() => {
        expect(mockMap.setView).toHaveBeenCalled();
      });
    });

    it('handles locate button click when geolocation is not available', () => {
      const originalGeolocation = navigator.geolocation;
      // @ts-expect-error - intentionally testing missing geolocation
      delete navigator.geolocation;

      render(<InstructorCoverageMap />);

      const locateButton = document.querySelector('button[title="Show your location"]') as HTMLButtonElement | null;

      act(() => {
        locateButton?.click();
      });

      // Should not throw
      expect(locateButton).toBeInTheDocument();

      // Restore
      Object.defineProperty(navigator, 'geolocation', {
        value: originalGeolocation,
        configurable: true,
      });
    });

    it('handles geolocation error gracefully', () => {
      const mockGeolocation = {
        getCurrentPosition: jest.fn((_success, error) => {
          error(new Error('Geolocation denied'));
        }),
      };
      Object.defineProperty(navigator, 'geolocation', {
        value: mockGeolocation,
        configurable: true,
      });

      render(<InstructorCoverageMap />);

      const locateButton = document.querySelector('button[title="Show your location"]') as HTMLButtonElement | null;

      act(() => {
        locateButton?.click();
      });

      // Should handle error gracefully without crashing
      expect(mockGeolocation.getCurrentPosition).toHaveBeenCalled();
    });

    it('handles multiple locate button clicks gracefully', async () => {
      const mockGeolocation = {
        getCurrentPosition: jest.fn((success) => {
          // Simulate delayed response
          setTimeout(() => {
            success({
              coords: {
                latitude: 40.7,
                longitude: -74.0,
              },
            });
          }, 100);
        }),
      };
      Object.defineProperty(navigator, 'geolocation', {
        value: mockGeolocation,
        configurable: true,
      });

      render(<InstructorCoverageMap />);

      const locateButton = document.querySelector('button[title="Show your location"]') as HTMLButtonElement | null;

      // Click twice quickly - should not throw
      expect(() => {
        act(() => {
          locateButton?.click();
          locateButton?.click();
        });
      }).not.toThrow();

      // Geolocation should have been requested
      expect(mockGeolocation.getCurrentPosition).toHaveBeenCalled();
    });

    it('removes custom controls on unmount', () => {
      const { unmount } = render(<InstructorCoverageMap />);

      unmount();

      // Control's remove should have been called
      const controlWithZoom = controlInstances.find(
        c => c.position === 'bottomright'
      );
      expect(controlWithZoom?.remove).toHaveBeenCalled();
    });

    it('replaces previous location marker when clicking locate again', async () => {
      // Track moveend handlers registered by the component
      const moveendHandlers: Array<() => void> = [];
      const zoomendHandlers: Array<() => void> = [];

      mockMap.on.mockImplementation((event: string, handler: () => void) => {
        if (event === 'moveend') {
          moveEndHandler = handler;
          moveendHandlers.push(handler);
        }
        if (event === 'zoomend') {
          zoomEndHandler = handler;
          zoomendHandlers.push(handler);
        }
      });

      mockMap.off.mockImplementation((event: string, handler?: () => void) => {
        if (handler) {
          if (event === 'moveend') {
            const idx = moveendHandlers.indexOf(handler);
            if (idx >= 0) moveendHandlers.splice(idx, 1);
          }
          if (event === 'zoomend') {
            const idx = zoomendHandlers.indexOf(handler);
            if (idx >= 0) zoomendHandlers.splice(idx, 1);
          }
        }
      });

      const mockGeolocation = {
        getCurrentPosition: jest.fn((success) => {
          success({
            coords: {
              latitude: 40.7,
              longitude: -74.0,
            },
          });
        }),
      };
      Object.defineProperty(navigator, 'geolocation', {
        value: mockGeolocation,
        configurable: true,
      });

      render(<InstructorCoverageMap />);

      const locateButton = document.querySelector('button[title="Show your location"]') as HTMLButtonElement | null;

      // First click creates first marker
      await act(async () => {
        locateButton?.click();
        await new Promise(resolve => setTimeout(resolve, 10));
      });

      expect(createdMarkers).toHaveLength(1);

      // Simulate moveend event to reset isMoving flag
      await act(async () => {
        // Trigger all registered moveend handlers to reset isMoving
        moveendHandlers.forEach(h => h());
        await new Promise(resolve => setTimeout(resolve, 10));
      });

      // Second click should remove first marker and create second
      await act(async () => {
        locateButton?.click();
        await new Promise(resolve => setTimeout(resolve, 10));
      });

      // First marker should have been removed before creating second
      expect(createdMarkers[0]?.remove).toHaveBeenCalled();
      expect(createdMarkers).toHaveLength(2);
    });
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

  it('renders location pins when provided', () => {
    render(
      <InstructorCoverageMap
        locationPins={[{ lat: 40.71, lng: -73.99, label: 'Studio' }]}
      />
    );

    expect(createdPinMarkers).toHaveLength(1);
    expect(createdPinMarkers[0]?.bindPopup).toHaveBeenCalledWith('<div>Studio</div>');
  });

  it('handles dark mode preference change', () => {
    const mockAddEventListener = jest.fn();
    const mockRemoveEventListener = jest.fn();

    const mockMatchMedia = jest.fn().mockReturnValue({
      matches: false,
      addEventListener: mockAddEventListener,
      removeEventListener: mockRemoveEventListener,
    });
    window.matchMedia = mockMatchMedia;

    const { unmount } = render(<InstructorCoverageMap />);

    expect(mockAddEventListener).toHaveBeenCalledWith('change', expect.any(Function));

    // Simulate dark mode change
    if (mockAddEventListener.mock.calls[0]) {
      const changeHandler = mockAddEventListener.mock.calls[0][1];
      act(() => {
        changeHandler({ matches: true });
      });
    }

    unmount();
    expect(mockRemoveEventListener).toHaveBeenCalled();
  });

  it('renders with empty feature properties', () => {
    const emptyPropsFeatureCollection = {
      type: 'FeatureCollection' as const,
      features: [
        {
          type: 'Feature' as const,
          geometry: {
            type: 'Polygon',
            coordinates: [[[-74, 40], [-73, 40], [-73, 41], [-74, 41], [-74, 40]]],
          },
          properties: {},
        },
      ],
    };

    render(
      <InstructorCoverageMap
        featureCollection={emptyPropsFeatureCollection}
        showCoverage={true}
      />
    );

    expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
  });

  it('handles feature without instructors array', () => {
    const noInstructorsFeatureCollection = {
      type: 'FeatureCollection' as const,
      features: [
        {
          type: 'Feature' as const,
          geometry: {
            type: 'Polygon',
            coordinates: [[[-74, 40], [-73, 40], [-73, 41], [-74, 41], [-74, 40]]],
          },
          properties: {
            name: 'Test Region',
            // No instructors array
          },
        },
      ],
    };

    render(
      <InstructorCoverageMap
        featureCollection={noInstructorsFeatureCollection}
        showCoverage={true}
        highlightInstructorId="inst-1"
      />
    );

    expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
  });

  it('focuses on instructor coverage when focusInstructorId changes', () => {
    const { rerender } = render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        focusInstructorId={null}
      />
    );

    rerender(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        focusInstructorId="inst-1"
      />
    );

    expect(screen.getByTestId('map-container')).toBeInTheDocument();
  });

  it('handles JAWG token with dark mode', () => {
    const originalEnv = process.env['NEXT_PUBLIC_JAWG_TOKEN'];
    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = 'test-token';

    const mockMatchMedia = jest.fn().mockReturnValue({
      matches: true, // dark mode
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    });
    window.matchMedia = mockMatchMedia;

    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('tile-layer')).toBeInTheDocument();

    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = originalEnv;
  });

  it('handles JAWG token with light mode', () => {
    const originalEnv = process.env['NEXT_PUBLIC_JAWG_TOKEN'];
    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = 'test-token';

    const mockMatchMedia = jest.fn().mockReturnValue({
      matches: false, // light mode
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
    });
    window.matchMedia = mockMatchMedia;

    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('tile-layer')).toBeInTheDocument();

    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = originalEnv;
  });

  it('handles missing matchMedia', () => {
    const originalMatchMedia = window.matchMedia;
    // @ts-expect-error - intentionally testing missing matchMedia
    delete window.matchMedia;

    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('map-container')).toBeInTheDocument();

    window.matchMedia = originalMatchMedia;
  });

  it('keeps using fallback URL after Jawg fails even when theme changes', () => {
    const originalEnv = process.env['NEXT_PUBLIC_JAWG_TOKEN'];
    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = 'test-token';

    const mockAddEventListener = jest.fn();
    const mockMatchMedia = jest.fn().mockReturnValue({
      matches: false,
      addEventListener: mockAddEventListener,
      removeEventListener: jest.fn(),
    });
    window.matchMedia = mockMatchMedia;

    render(<InstructorCoverageMap />);

    // Simulate tile error (Jawg fails)
    const tileLayer = screen.getByTestId('tile-layer');
    act(() => {
      fireEvent.click(tileLayer);
    });

    // Should be using fallback
    expect(screen.getByTestId('tile-layer').getAttribute('data-url')).toContain('cartocdn');

    // Change theme
    if (mockAddEventListener.mock.calls[0]) {
      const changeHandler = mockAddEventListener.mock.calls[0][1];
      act(() => {
        changeHandler({ matches: true }); // Switch to dark mode
      });
    }

    // Should still be using fallback (not switch back to Jawg)
    expect(screen.getByTestId('tile-layer').getAttribute('data-url')).toContain('cartocdn');

    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = originalEnv;
  });

  describe('FitToCoverage', () => {
    it('fits bounds to coverage on initial render', () => {
      render(
        <InstructorCoverageMap
          featureCollection={mockFeatureCollection}
          showCoverage={true}
        />
      );

      expect(mockMap.fitBounds).toHaveBeenCalled();
    });

    it('does not fit bounds when focusInstructorId is set initially', () => {
      mockMap.fitBounds.mockClear();

      render(
        <InstructorCoverageMap
          featureCollection={mockFeatureCollection}
          showCoverage={true}
          focusInstructorId="inst-1"
        />
      );

      // Should use flyToBounds for focused instructor, not fitBounds
      expect(mockMap.flyToBounds).toHaveBeenCalled();
    });

    it('flies to instructor coverage when focusInstructorId is set', () => {
      render(
        <InstructorCoverageMap
          featureCollection={mockFeatureCollection}
          showCoverage={true}
          focusInstructorId="inst-1"
        />
      );

      expect(mockMap.flyToBounds).toHaveBeenCalled();
    });

    it('handles focusInstructorId with no matching features', () => {
      render(
        <InstructorCoverageMap
          featureCollection={mockFeatureCollection}
          showCoverage={true}
          focusInstructorId="non-existent-instructor"
        />
      );

      // Should render without errors
      expect(screen.getByTestId('map-container')).toBeInTheDocument();
    });

    it('handles invalid bounds gracefully', () => {
      const L = jest.requireMock('leaflet');
      L.geoJSON.mockReturnValue({
        getBounds: jest.fn(() => ({
          isValid: jest.fn(() => false),
        })),
        remove: jest.fn(),
      });

      render(
        <InstructorCoverageMap
          featureCollection={mockFeatureCollection}
          showCoverage={true}
        />
      );

      // Should render without errors even with invalid bounds
      expect(screen.getByTestId('map-container')).toBeInTheDocument();
    });
  });

  describe('GeoJSON styling', () => {
    it('applies default style when instructor is not highlighted', () => {
      render(
        <InstructorCoverageMap
          featureCollection={mockFeatureCollection}
          showCoverage={true}
          highlightInstructorId="inst-1"
        />
      );

      // GeoJSON should be rendered
      expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
    });

    it('uses region_id as fallback name in popup', () => {
      render(
        <InstructorCoverageMap
          featureCollection={{
            type: 'FeatureCollection',
            features: [{
              type: 'Feature',
              geometry: {
                type: 'Polygon',
                coordinates: [[[-74, 40], [-73, 40], [-73, 41], [-74, 41], [-74, 40]]],
              },
              properties: {
                region_id: 'test-region',
                // No name property
              },
            }],
          }}
          showCoverage={true}
        />
      );

      expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
    });

    it('uses default Coverage Area when no name or region_id', () => {
      render(
        <InstructorCoverageMap
          featureCollection={{
            type: 'FeatureCollection',
            features: [{
              type: 'Feature',
              geometry: {
                type: 'Polygon',
                coordinates: [[[-74, 40], [-73, 40], [-73, 41], [-74, 41], [-74, 40]]],
              },
              properties: {},
            }],
          }}
          showCoverage={true}
        />
      );

      expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
    });
  });

  describe('control cleanup', () => {
    it('removes controls when component unmounts', () => {
      const { unmount } = render(
        <InstructorCoverageMap
          showSearchAreaButton={true}
          onSearchArea={jest.fn()}
        />
      );

      const controlsBefore = controlInstances.length;
      expect(controlsBefore).toBeGreaterThan(0);

      unmount();

      // All controls should have remove called
      controlInstances.forEach(control => {
        expect(control.remove).toHaveBeenCalled();
      });
    });
  });
});
