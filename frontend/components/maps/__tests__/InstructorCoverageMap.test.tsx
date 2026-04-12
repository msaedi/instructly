import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';

import InstructorCoverageMap from '../InstructorCoverageMap';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

let moveEndHandler: (() => void) | null = null;
let zoomEndHandler: (() => void) | null = null;

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

type MarkerRecord = {
  remove: jest.Mock;
  iconHtml: string;
  title?: string;
};

const markerRecords: MarkerRecord[] = [];
const controlInstances: Array<{
  onAdd: ((map: unknown) => HTMLElement) | undefined;
  remove: jest.Mock;
  position: string;
}> = [];

type MockMediaQueryList = MediaQueryList & {
  trigger: (matches: boolean) => void;
};

const setMatchMediaMock = (matches = false): MockMediaQueryList => {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  let currentMatches = matches;
  const mediaQuery = {
    get matches() {
      return currentMatches;
    },
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: jest.fn((_event: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener);
    }),
    removeEventListener: jest.fn(
      (_event: string, listener: (event: MediaQueryListEvent) => void) => {
        listeners.delete(listener);
      }
    ),
    addListener: jest.fn(),
    removeListener: jest.fn(),
    dispatchEvent: jest.fn(),
    trigger(nextMatches: boolean) {
      currentMatches = nextMatches;
      listeners.forEach((listener) => listener({ matches: nextMatches } as MediaQueryListEvent));
    },
  } as MockMediaQueryList;

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: jest.fn().mockImplementation(() => mediaQuery),
  });

  return mediaQuery;
};

const setGeolocationMock = (
  value:
    | {
        getCurrentPosition: jest.Mock;
      }
    | undefined
) => {
  Object.defineProperty(global.navigator, 'geolocation', {
    configurable: true,
    value,
  });
};

jest.mock('react-leaflet-cluster', () => {
  const MockMarkerClusterGroup = ({
    children,
    chunkedLoading,
    maxClusterRadius,
    showCoverageOnHover,
    spiderfyOnMaxZoom,
    iconCreateFunction,
  }: {
    children: React.ReactNode;
    chunkedLoading?: boolean;
    maxClusterRadius?: number;
    showCoverageOnHover?: boolean;
    spiderfyOnMaxZoom?: boolean;
    iconCreateFunction?: (cluster: { getChildCount: () => number }) => { options?: { html?: string } };
  }) => {
    const childCount = React.Children.toArray(children).length;
    const clusterIcon = iconCreateFunction?.({
      getChildCount: () => childCount,
    });

    return (
      <div
        data-testid="marker-cluster-group"
        data-chunked-loading={chunkedLoading ? 'true' : 'false'}
        data-max-cluster-radius={String(maxClusterRadius ?? '')}
        data-show-coverage-on-hover={showCoverageOnHover ? 'true' : 'false'}
        data-spiderfy-on-max-zoom={spiderfyOnMaxZoom ? 'true' : 'false'}
        data-cluster-icon-html={clusterIcon?.options?.html ?? ''}
      >
        {children}
      </div>
    );
  };

  MockMarkerClusterGroup.displayName = 'MockMarkerClusterGroup';

  return {
    __esModule: true,
    default: MockMarkerClusterGroup,
  };
});

jest.mock('react-leaflet', () => ({
  MapContainer: ({
    children,
    whenReady,
  }: {
    children: React.ReactNode;
    whenReady?: () => void;
  }) => {
    React.useEffect(() => {
      whenReady?.();
    }, [whenReady]);

    return <div data-testid="map-container">{children}</div>;
  },
  TileLayer: ({
    url,
    eventHandlers,
  }: {
    url: string;
    eventHandlers?: { tileerror?: () => void };
  }) => (
    <button
      type="button"
      data-testid="tile-layer"
      data-url={url}
      onClick={() => eventHandlers?.tileerror?.()}
    />
  ),
  GeoJSON: ({
    data,
    style,
    onEachFeature,
  }: {
    data: { features?: Array<Record<string, unknown>> };
    style?: (feature: unknown) => object;
    onEachFeature?: (feature: unknown, layer: unknown) => void;
  }) => {
    const features = Array.isArray(data?.features) ? data.features : [];

    return (
      <div data-testid="geojson-layer">
        {features.map((feature, index) => {
          const properties = (feature as { properties?: { name?: string; region_id?: string } } | undefined)
            ?.properties;
          const mockLayer = {
            bindPopup: jest.fn(),
            on: jest.fn(),
          };
          const styleResult = style?.(feature);
          onEachFeature?.(feature, mockLayer);
          const clickHandler = (
            mockLayer.on as jest.Mock
          ).mock.calls.find((call) => typeof call[0]?.click === 'function')?.[0]?.click as
            | (() => void)
            | undefined;
          const key = String(properties?.name || properties?.region_id || '') || `feature-${index}`;

          return (
            <button
              key={key}
              type="button"
              data-testid={`geojson-feature-${index}`}
              data-style={JSON.stringify(styleResult ?? {})}
              onClick={() => clickHandler?.()}
            >
              {key}
            </button>
          );
        })}
      </div>
    );
  },
  AttributionControl: () => <div data-testid="attribution-control" />,
  Marker: ({
    children,
    icon,
    eventHandlers,
    position,
    title,
  }: {
    children?: React.ReactNode;
    icon?: { options?: { html?: string } };
    eventHandlers?: {
      mouseover?: () => void;
      mouseout?: () => void;
      click?: () => void;
    };
    position: [number, number];
    title?: string;
  }) => {
    const iconHtml = icon?.options?.html ?? '';
    React.useEffect(() => {
      const record: MarkerRecord = {
        remove: jest.fn(),
        iconHtml,
        ...(title ? { title } : {}),
      };
      markerRecords.push(record);
      return () => {
        record.remove();
      };
    }, [iconHtml, title]);

    return (
      <button
        type="button"
        data-testid="map-marker"
        data-lat={String(position[0])}
        data-lng={String(position[1])}
        data-title={title ?? ''}
        data-icon-html={iconHtml}
        onMouseOver={() => eventHandlers?.mouseover?.()}
        onMouseOut={() => eventHandlers?.mouseout?.()}
        onClick={() => eventHandlers?.click?.()}
      >
        {children}
      </button>
    );
  },
  Popup: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="marker-popup">{children}</div>
  ),
  useMap: () => mockMap,
}));

jest.mock('leaflet', () => {
  const controlFactory = jest.fn().mockImplementation(function mockControl(
    this: { position: string },
    options?: { position?: string }
  ) {
    this.position = options?.position || 'bottomright';
    const control = {
      position: this.position,
      onAdd: undefined as ((map: unknown) => HTMLElement) | undefined,
      remove: jest.fn(),
      addTo: jest.fn().mockImplementation((map: unknown) => {
        if (control.onAdd) {
          document.body.appendChild(control.onAdd(map));
        }
        controlInstances.push(control);
        return control;
      }),
    };
    return control;
  });

  const divIcon = jest.fn((options: Record<string, unknown>) => ({ options }));

  return {
    __esModule: true,
    default: {
      Control: controlFactory,
      DomUtil: {
        create: jest.fn((tag: string) => document.createElement(tag)),
      },
      DomEvent: {
        disableClickPropagation: jest.fn(),
        disableScrollPropagation: jest.fn(),
      },
      geoJSON: jest.fn(() => ({
        getBounds: jest.fn(() => ({
          extend: jest.fn(function extend() {
            return this;
          }),
          isValid: jest.fn(() => true),
          getNorth: () => 41,
          getSouth: () => 40,
          getEast: () => -73,
          getWest: () => -74,
        })),
        remove: jest.fn(),
      })),
      circleMarker: jest.fn(() => ({
        addTo: jest.fn().mockReturnThis(),
        remove: jest.fn(),
      })),
      divIcon,
      latLngBounds: jest.fn(() => ({
        extend: jest.fn(function extend() {
          return this;
        }),
        isValid: jest.fn(() => true),
      })),
    },
    Control: controlFactory,
    DomUtil: {
      create: jest.fn((tag: string) => document.createElement(tag)),
    },
    DomEvent: {
      disableClickPropagation: jest.fn(),
      disableScrollPropagation: jest.fn(),
    },
    geoJSON: jest.fn(() => ({
      getBounds: jest.fn(() => ({
        extend: jest.fn(function extend() {
          return this;
        }),
        isValid: jest.fn(() => true),
        getNorth: () => 41,
        getSouth: () => 40,
        getEast: () => -73,
        getWest: () => -74,
      })),
      remove: jest.fn(),
    })),
    circleMarker: jest.fn(() => ({
      addTo: jest.fn().mockReturnThis(),
      remove: jest.fn(),
    })),
    divIcon,
    latLngBounds: jest.fn(() => ({
      extend: jest.fn(function extend() {
        return this;
      }),
      isValid: jest.fn(() => true),
    })),
  };
});

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
        },
      },
    ],
  };

  beforeEach(() => {
    jest.clearAllMocks();
    markerRecords.length = 0;
    controlInstances.length = 0;
    moveEndHandler = null;
    zoomEndHandler = null;
    document.body.innerHTML = '';
    setMatchMediaMock(false);
    setGeolocationMock({
      getCurrentPosition: jest.fn(),
    });
    mockMap.getCenter.mockReturnValue({ lat: 40.7831, lng: -73.9712 });
    mockMap.getZoom.mockReturnValue(12);
  });

  it('renders the map shell and fallback tile provider switching', () => {
    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('map-container')).toBeInTheDocument();
    expect(screen.getByTestId('tile-layer')).toBeInTheDocument();
    expect(screen.getByTestId('attribution-control')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('tile-layer'));

    expect(screen.getByTestId('tile-layer')).toHaveAttribute(
      'data-url',
      expect.stringContaining('cartocdn')
    );
  });

  it('subscribes to color scheme changes for Jawg tiles and cleans up the listener on unmount', () => {
    const priorJawgToken = process.env['NEXT_PUBLIC_JAWG_TOKEN'];
    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = 'jawg-token';
    const mediaQuery = setMatchMediaMock(true);

    const { unmount } = render(<InstructorCoverageMap />);

    expect(screen.getByTestId('tile-layer')).toHaveAttribute(
      'data-url',
      expect.stringContaining('jawg-dark')
    );

    act(() => {
      mediaQuery.trigger(false);
    });

    expect(screen.getByTestId('tile-layer')).toHaveAttribute(
      'data-url',
      expect.stringContaining('jawg-sunny')
    );

    const registeredHandler = (mediaQuery.addEventListener as jest.Mock).mock.calls[0]?.[1];

    unmount();

    expect(mediaQuery.addEventListener).toHaveBeenCalledWith('change', expect.any(Function));
    expect(mediaQuery.removeEventListener).toHaveBeenCalledWith('change', registeredHandler);

    if (typeof priorJawgToken === 'string') {
      process.env['NEXT_PUBLIC_JAWG_TOKEN'] = priorJawgToken;
    } else {
      delete process.env['NEXT_PUBLIC_JAWG_TOKEN'];
    }
  });

  it('renders safely when matchMedia is unavailable', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: undefined,
    });

    render(<InstructorCoverageMap />);

    expect(screen.getByTestId('tile-layer')).toHaveAttribute(
      'data-url',
      expect.stringContaining('cartocdn')
    );
  });

  it('calls onAreaClick with the selected coverage feature ids', () => {
    const onAreaClick = jest.fn();

    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        showCoverage={true}
        onAreaClick={onAreaClick}
      />
    );

    fireEvent.click(screen.getByTestId('geojson-feature-0'));

    expect(onAreaClick).toHaveBeenCalledWith('Upper West Side', ['inst-1', 'inst-2']);
  });

  it('handles GeoJSON fallback properties and highlighted coverage styling', () => {
    const onAreaClick = jest.fn();

    render(
      <InstructorCoverageMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              geometry: null,
              properties: {
                region_id: 'chelsea',
                instructors: ['inst-3', 42, ''] as unknown as string[],
              },
            },
            {
              type: 'Feature',
              geometry: null,
            },
          ],
        }}
        highlightInstructorId="inst-3"
        onAreaClick={onAreaClick}
      />
    );

    expect(screen.getByTestId('geojson-feature-0')).toHaveTextContent('chelsea');
    expect(screen.getByTestId('geojson-feature-0')).toHaveAttribute(
      'data-style',
      JSON.stringify({ color: 'var(--color-brand-dark)', weight: 2, fillOpacity: 0.35 })
    );
    expect(screen.getByTestId('geojson-feature-1')).toHaveTextContent('feature-1');

    fireEvent.click(screen.getByTestId('geojson-feature-0'));
    fireEvent.click(screen.getByTestId('geojson-feature-1'));

    expect(onAreaClick).toHaveBeenNthCalledWith(1, 'chelsea', ['inst-3']);
    expect(onAreaClick).toHaveBeenNthCalledWith(2, 'Coverage Area', []);
  });

  it('renders a photo pin with a popup when no click override is provided', () => {
    render(
      <InstructorCoverageMap
        locationPins={[
          {
            lat: 40.71,
            lng: -73.99,
            label: 'Lower East Side',
            instructorId: 'inst-1',
            displayName: 'Ava L.',
            profilePictureUrl: 'https://cdn.example.com/ava.jpg',
          },
        ]}
      />
    );

    const marker = screen.getByTestId('map-marker');
    const iconHtml = marker.getAttribute('data-icon-html') ?? '';

    expect(iconHtml).toContain('data-photo-pin="true"');
    expect(iconHtml).toContain('src="https://cdn.example.com/ava.jpg"');
    expect(iconHtml).toContain('alt="Ava L."');
    expect(screen.getByTestId('marker-popup')).toHaveTextContent('Lower East Side');
  });

  it('renders the lavender fallback pin when no profile photo url is available', () => {
    render(
      <InstructorCoverageMap
        locationPins={[
          {
            lat: 40.71,
            lng: -73.99,
            label: 'Fallback Studio',
            instructorId: 'inst-1',
            displayName: 'Ava L.',
            profilePictureUrl: null,
          },
        ]}
      />
    );

    const iconHtml = screen.getByTestId('map-marker').getAttribute('data-icon-html') ?? '';

    expect(iconHtml).toContain('data-photo-fallback="true"');
    expect(iconHtml).not.toContain('<img');
    expect(iconHtml).toContain('#F3E8FF');
  });

  it('skips the marker layer when all provided pins have invalid coordinates', () => {
    render(
      <InstructorCoverageMap
        locationPins={[
          {
            lat: Number.NaN,
            lng: -73.99,
            instructorId: 'inst-1',
          },
          {
            lat: 40.71,
            lng: Number.POSITIVE_INFINITY,
            instructorId: 'inst-2',
          },
        ]}
      />
    );

    expect(screen.queryByTestId('marker-cluster-group')).not.toBeInTheDocument();
    expect(screen.queryByTestId('map-marker')).not.toBeInTheDocument();
  });

  it('uses label and generic instructor fallbacks when a pin lacks display metadata', () => {
    render(
      <InstructorCoverageMap
        locationPins={[
          {
            lat: 40.71,
            lng: -73.99,
            label: 'Label only',
          },
          {
            lat: 40.72,
            lng: -73.98,
          },
        ]}
      />
    );

    const markers = screen.getAllByTestId('map-marker');

    expect(markers[0]).toHaveAttribute('data-title', 'Label only');
    expect(markers[0]).toHaveAttribute(
      'data-icon-html',
      expect.stringContaining('aria-label="Label only location pin"')
    );
    expect(markers[1]).toHaveAttribute('data-title', '');
    expect(markers[1]).toHaveAttribute(
      'data-icon-html',
      expect.stringContaining('aria-label="Instructor location pin"')
    );
  });

  it('fires onPinHover on mouseover and clears it on mouseout', () => {
    const onPinHover = jest.fn();

    render(
      <InstructorCoverageMap
        locationPins={[
          {
            lat: 40.71,
            lng: -73.99,
            instructorId: 'inst-1',
            displayName: 'Ava L.',
          },
        ]}
        onPinHover={onPinHover}
      />
    );

    const marker = screen.getByTestId('map-marker');
    fireEvent.mouseOver(marker);
    fireEvent.mouseOut(marker);

    expect(onPinHover).toHaveBeenNthCalledWith(1, 'inst-1');
    expect(onPinHover).toHaveBeenNthCalledWith(2, null);
  });

  it('fires onPinClick with the matching instructor id and suppresses popups when click sync is enabled', () => {
    const onPinClick = jest.fn();

    render(
      <InstructorCoverageMap
        locationPins={[
          {
            lat: 40.71,
            lng: -73.99,
            label: 'No Popup',
            instructorId: 'inst-1',
            displayName: 'Ava L.',
          },
        ]}
        onPinClick={onPinClick}
      />
    );

    fireEvent.click(screen.getByTestId('map-marker'));

    expect(onPinClick).toHaveBeenCalledWith('inst-1');
    expect(screen.queryByTestId('marker-popup')).not.toBeInTheDocument();
  });

  it('applies hover and focus pin states from instructor ids', () => {
    render(
      <InstructorCoverageMap
        locationPins={[
          {
            lat: 40.71,
            lng: -73.99,
            instructorId: 'inst-1',
            displayName: 'Hover Target',
          },
          {
            lat: 40.72,
            lng: -73.98,
            instructorId: 'inst-2',
            displayName: 'Focus Target',
          },
        ]}
        highlightInstructorId="inst-1"
        focusInstructorId="inst-2"
      />
    );

    const markers = screen.getAllByTestId('map-marker');
    expect(markers[0]).toHaveAttribute('data-icon-html', expect.stringContaining('data-pin-state="hovered"'));
    expect(markers[1]).toHaveAttribute('data-icon-html', expect.stringContaining('data-pin-state="focused"'));
  });

  it('configures clustering with branded cluster icons', () => {
    render(
      <InstructorCoverageMap
        locationPins={[
          { lat: 40.71, lng: -73.99, instructorId: 'inst-1', displayName: 'Ava L.' },
          { lat: 40.7102, lng: -73.9901, instructorId: 'inst-2', displayName: 'Ben Q.' },
          { lat: 40.7103, lng: -73.9902, instructorId: 'inst-3', displayName: 'Cara P.' },
        ]}
      />
    );

    const clusterGroup = screen.getByTestId('marker-cluster-group');
    expect(clusterGroup).toHaveAttribute('data-chunked-loading', 'true');
    expect(clusterGroup).toHaveAttribute('data-max-cluster-radius', '40');
    expect(clusterGroup).toHaveAttribute('data-show-coverage-on-hover', 'false');
    expect(clusterGroup).toHaveAttribute('data-spiderfy-on-max-zoom', 'true');
    expect(clusterGroup.getAttribute('data-cluster-icon-html')).toContain('data-cluster-count="3"');
  });

  it('fits to coverage and pin bounds, and focuses with flyToBounds when instructed', async () => {
    const { rerender } = render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        locationPins={[
          { lat: 40.71, lng: -73.99, instructorId: 'inst-1', displayName: 'Ava L.' },
        ]}
      />
    );

    await waitFor(() => {
      expect(mockMap.fitBounds).toHaveBeenCalled();
    });

    rerender(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        locationPins={[
          { lat: 40.71, lng: -73.99, instructorId: 'inst-1', displayName: 'Ava L.' },
        ]}
        focusInstructorId="inst-1"
      />
    );

    expect(mockMap.flyToBounds).toHaveBeenCalled();
  });

  it('fits using a string height and skips refits for unchanged data keys', async () => {
    const initialPins = [
      { lat: 40.71, lng: -73.99, instructorId: 'inst-1', displayName: 'Ava L.' },
    ];
    const { container, rerender } = render(
      <InstructorCoverageMap
        height="50vh"
        featureCollection={mockFeatureCollection}
        locationPins={initialPins}
      />
    );

    expect(container.firstChild).toHaveStyle({ height: '50vh' });

    await waitFor(() => {
      expect(mockMap.fitBounds).toHaveBeenCalledTimes(1);
    });

    rerender(
      <InstructorCoverageMap
        height="50vh"
        featureCollection={mockFeatureCollection}
        locationPins={[...initialPins]}
      />
    );

    await waitFor(() => {
      expect(mockMap.fitBounds).toHaveBeenCalledTimes(1);
    });
  });

  it('handles repeated fit initialization safely under strict mode', () => {
    render(
      <React.StrictMode>
        <InstructorCoverageMap featureCollection={mockFeatureCollection} />
      </React.StrictMode>
    );

    expect(screen.getByTestId('geojson-layer')).toBeInTheDocument();
  });

  it('treats truthy non-array location pin payloads as empty map pins without crashing', () => {
    const weirdLocationPins = { length: 1 } as unknown as NonNullable<
      Parameters<typeof InstructorCoverageMap>[0]['locationPins']
    >;

    render(
      <InstructorCoverageMap
        showCoverage={false}
        locationPins={weirdLocationPins}
      />
    );

    expect(screen.queryByTestId('marker-cluster-group')).not.toBeInTheDocument();
    expect(mockMap.fitBounds).not.toHaveBeenCalled();
  });

  it('skips invalid initial coverage bounds', async () => {
    const leafletMock = jest.requireMock('leaflet') as {
      default: {
        geoJSON: jest.Mock;
      };
    };

    leafletMock.default.geoJSON.mockImplementationOnce(() => ({
      getBounds: jest.fn(() => ({
        isValid: jest.fn(() => false),
      })),
      remove: jest.fn(),
    }));

    render(<InstructorCoverageMap featureCollection={mockFeatureCollection} />);

    await waitFor(() => {
      expect(mockMap.fitBounds).not.toHaveBeenCalled();
    });
  });

  it('skips focus flyToBounds when focused coverage and pins do not resolve to valid bounds', async () => {
    const leafletMock = jest.requireMock('leaflet') as {
      default: {
        geoJSON: jest.Mock;
        latLngBounds: jest.Mock;
      };
    };

    leafletMock.default.geoJSON
      .mockImplementationOnce(() => ({
        getBounds: jest.fn(() => ({
          extend: jest.fn(function extend() {
            return this;
          }),
          isValid: jest.fn(() => true),
        })),
        remove: jest.fn(),
      }))
      .mockImplementationOnce(() => ({
        getBounds: jest.fn(() => ({
          isValid: jest.fn(() => false),
        })),
        remove: jest.fn(),
      }));
    leafletMock.default.latLngBounds
      .mockImplementationOnce(() => ({
        isValid: jest.fn(() => true),
      }))
      .mockImplementationOnce(() => ({
        isValid: jest.fn(() => false),
      }));

    const { rerender } = render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        locationPins={[
          { lat: 40.71, lng: -73.99, instructorId: 'inst-1', displayName: 'Ava L.' },
        ]}
      />
    );

    await waitFor(() => {
      expect(mockMap.fitBounds).toHaveBeenCalled();
    });

    mockMap.flyToBounds.mockClear();

    rerender(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        locationPins={[
          { lat: 40.71, lng: -73.99, instructorId: 'inst-1', displayName: 'Ava L.' },
        ]}
        focusInstructorId="inst-1"
      />
    );

    await waitFor(() => {
      expect(mockMap.flyToBounds).not.toHaveBeenCalled();
    });
  });

  it('skips focus flyToBounds when the focused instructor matches neither coverage nor pins', async () => {
    render(
      <InstructorCoverageMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              geometry: null,
            },
          ],
        }}
        locationPins={[
          { lat: 40.71, lng: -73.99, instructorId: 'inst-2', displayName: 'Other Instructor' },
        ]}
        focusInstructorId="inst-1"
      />
    );

    await waitFor(() => {
      expect(mockMap.flyToBounds).not.toHaveBeenCalled();
    });
  });

  it('focuses coverage even when location pins are omitted entirely', async () => {
    render(
      <InstructorCoverageMap
        featureCollection={mockFeatureCollection}
        focusInstructorId="inst-1"
      />
    );

    await waitFor(() => {
      expect(mockMap.flyToBounds).toHaveBeenCalled();
    });
  });

  it('tracks map bounds through move and zoom events', () => {
    const onBoundsChange = jest.fn();

    render(<InstructorCoverageMap onBoundsChange={onBoundsChange} />);

    act(() => {
      moveEndHandler?.();
      zoomEndHandler?.();
    });

    expect(onBoundsChange).toHaveBeenCalledTimes(2);
  });

  it('does not mount the search area control when no callback is provided', () => {
    render(<InstructorCoverageMap showSearchAreaButton={true} />);

    expect(screen.queryByRole('button', { name: /search this area/i })).not.toBeInTheDocument();
    expect(controlInstances.filter((control) => control.position === 'topleft')).toHaveLength(0);
  });

  it('mounts the search area control, handles hover and click, and removes it on unmount', () => {
    const onSearchArea = jest.fn();
    const { unmount } = render(
      <InstructorCoverageMap showSearchAreaButton={true} onSearchArea={onSearchArea} />
    );

    const searchAreaButton = screen.getByRole('button', { name: /search this area/i });
    const searchAreaControl = controlInstances.find((control) => control.position === 'topleft');

    fireEvent.mouseOver(searchAreaButton);
    expect(searchAreaButton).toHaveStyle({ boxShadow: '0 4px 12px rgba(0,0,0,0.2)' });

    fireEvent.mouseOut(searchAreaButton);
    expect(searchAreaButton).toHaveStyle({ boxShadow: '0 2px 8px rgba(0,0,0,0.15)' });

    fireEvent.click(searchAreaButton);
    expect(onSearchArea).toHaveBeenCalledTimes(1);

    unmount();

    expect(searchAreaControl?.remove).toHaveBeenCalledTimes(1);
  });

  it('handles locate, repeat locate, zoom, and cleanup through the custom control buttons', () => {
    const leafletMock = jest.requireMock('leaflet') as {
      default: {
        circleMarker: jest.Mock;
      };
    };
    const getCurrentPosition = jest.fn<
      void,
      [
        PositionCallback,
        PositionErrorCallback | null | undefined,
        PositionOptions | undefined,
      ]
    >();
    const successCallbacks: PositionCallback[] = [];

    getCurrentPosition.mockImplementation((success) => {
      successCallbacks.push(success);
    });
    setGeolocationMock({ getCurrentPosition });

    const { unmount } = render(<InstructorCoverageMap />);

    const locateButton = screen.getByTitle('Show your location');
    const zoomInButton = screen.getByTitle('Zoom in');
    const zoomOutButton = screen.getByTitle('Zoom out');
    const customControl = controlInstances.find((control) => control.position === 'bottomright');

    fireEvent.click(locateButton);
    expect(getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      { enableHighAccuracy: true, timeout: 8000 }
    );

    act(() => {
      successCallbacks[0]?.({
        coords: {
          latitude: 40.71,
          longitude: -73.99,
        },
      } as GeolocationPosition);
    });

    expect(mockMap.stop).toHaveBeenCalled();
    expect(mockMap.flyTo).toHaveBeenCalledWith([40.71, -73.99], 14, { animate: false });

    const firstLocationMarker = leafletMock.default.circleMarker.mock.results[0]?.value as {
      addTo: jest.Mock;
      remove: jest.Mock;
    };
    expect(firstLocationMarker.addTo).toHaveBeenCalledWith(mockMap);

    fireEvent.click(locateButton);
    act(() => {
      successCallbacks[1]?.({
        coords: {
          latitude: 40.72,
          longitude: -73.98,
        },
      } as GeolocationPosition);
    });

    expect(leafletMock.default.circleMarker).toHaveBeenCalledTimes(1);

    act(() => {
      moveEndHandler?.();
      zoomEndHandler?.();
    });

    mockMap.getCenter.mockReturnValue({ lat: 40.7201, lng: -73.9801 });

    fireEvent.click(locateButton);
    act(() => {
      successCallbacks[2]?.({
        coords: {
          latitude: 40.7202,
          longitude: -73.9801,
        },
      } as GeolocationPosition);
    });

    expect(mockMap.setView).toHaveBeenCalledWith([40.7202, -73.9801], 14, { animate: false });
    expect(firstLocationMarker.remove).toHaveBeenCalledTimes(1);

    const secondLocationMarker = leafletMock.default.circleMarker.mock.results[1]?.value as {
      addTo: jest.Mock;
    };
    expect(secondLocationMarker.addTo).toHaveBeenCalledWith(mockMap);
    expect(mockMap.off).toHaveBeenCalledWith('moveend', expect.any(Function));
    expect(mockMap.off).toHaveBeenCalledWith('zoomend', expect.any(Function));

    fireEvent.click(zoomInButton);
    expect(mockMap.zoomIn).toHaveBeenCalledWith(1);

    fireEvent.click(zoomOutButton);
    expect(mockMap.zoomOut).toHaveBeenCalledWith(1);

    unmount();

    expect(customControl?.remove).toHaveBeenCalledTimes(1);
  });

  it('ignores locate clicks when geolocation is unavailable', () => {
    setGeolocationMock(undefined);

    render(<InstructorCoverageMap />);

    fireEvent.click(screen.getByTitle('Show your location'));

    expect(mockMap.flyTo).not.toHaveBeenCalled();
    expect(mockMap.setView).not.toHaveBeenCalled();
    expect(mockMap.stop).not.toHaveBeenCalled();
  });

  it('handles geolocation errors and locate flows even when the map stop method is unavailable', () => {
    const successCallbacks: PositionCallback[] = [];
    const errorCallbacks: Array<PositionErrorCallback | null | undefined> = [];
    const getCurrentPosition = jest.fn<
      void,
      [
        PositionCallback,
        PositionErrorCallback | null | undefined,
        PositionOptions | undefined,
      ]
    >((success, error) => {
      successCallbacks.push(success);
      errorCallbacks.push(error);
    });
    const originalStop = mockMap.stop;

    setGeolocationMock({ getCurrentPosition });
    (mockMap as { stop?: unknown }).stop = undefined;

    render(<InstructorCoverageMap />);

    fireEvent.click(screen.getByTitle('Show your location'));
    act(() => {
      successCallbacks[0]?.({
        coords: {
          latitude: 40.73,
          longitude: -73.97,
        },
      } as GeolocationPosition);
    });
    act(() => {
      errorCallbacks[0]?.({} as GeolocationPositionError);
    });

    expect(mockMap.flyTo).toHaveBeenCalledWith([40.73, -73.97], 14, { animate: false });

    (mockMap as { stop?: unknown }).stop = originalStop;
  });
});
