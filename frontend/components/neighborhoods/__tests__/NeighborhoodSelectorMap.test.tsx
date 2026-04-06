import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Feature, Polygon } from 'geojson';

import NeighborhoodSelectorMap from '../NeighborhoodSelectorMap';

type MockFeature = Feature<
  Polygon,
  {
    id: string;
    display_key: string;
    display_name: string;
    borough: string;
    region_name: string;
  }
>;

const mockMap = {
  fitBounds: jest.fn(),
};

let currentMap: typeof mockMap | null = mockMap;
const renderedLayers: MockLayer[] = [];
const tileLayerState: {
  url: string;
  onTileError: (() => void) | null;
} = {
  url: '',
  onTileError: null,
};
const mediaQueryListeners = new Set<(event: MediaQueryListEvent) => void>();
let prefersDarkMode = false;

type MockLayer = {
  feature: MockFeature;
  bindTooltip: jest.Mock;
  on: jest.Mock;
  setStyle: jest.Mock;
  getBounds: () => {
    extend: jest.Mock;
    getSouthWest: jest.Mock;
    getNorthEast: jest.Mock;
  };
  _events: Record<string, () => void>;
};

jest.mock('react-leaflet', () => {
  const React = require('react') as typeof import('react');

  return {
    MapContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="map-container">{children}</div>
    ),
    TileLayer: ({
      url,
      eventHandlers,
    }: {
      url: string;
      eventHandlers?: { tileerror?: () => void };
    }) => {
      tileLayerState.url = url;
      tileLayerState.onTileError = eventHandlers?.tileerror ?? null;
      return (
        <button
          type="button"
          data-testid="tile-layer"
          data-url={url}
          onClick={() => eventHandlers?.tileerror?.()}
        />
      );
    },
    AttributionControl: () => <div data-testid="attribution-control" />,
    useMap: () => currentMap,
    GeoJSON: React.forwardRef(function MockGeoJson(
      {
        data,
        style,
        onEachFeature,
      }: {
        data: { features: MockFeature[] };
        style?: (feature: MockFeature) => Record<string, unknown>;
        onEachFeature?: (feature: MockFeature, layer: MockLayer) => void;
      },
      ref: React.ForwardedRef<{ eachLayer: (fn: (layer: MockLayer) => void) => void }>,
    ) {
      const layers = data.features.map((feature) => {
        const events: Record<string, () => void> = {};
        const bounds = {
          extend: jest.fn(),
          getSouthWest: jest.fn(() => ({ lat: 40.7, lng: -74 })),
          getNorthEast: jest.fn(() => ({ lat: 40.8, lng: -73.9 })),
        };
        const layer: MockLayer = {
          feature,
          bindTooltip: jest.fn(),
          on: jest.fn((eventMap: Record<string, () => void>) => {
            Object.assign(events, eventMap);
          }),
          setStyle: jest.fn(),
          getBounds: () => bounds,
          _events: events,
        };
        onEachFeature?.(feature, layer);
        if (style) {
          layer.setStyle(style(feature));
        }
        return layer;
      });
      renderedLayers.splice(0, renderedLayers.length, ...layers);

      React.useEffect(() => {
        const geoJsonLayer = {
          eachLayer: (callback: (layer: MockLayer) => void) => {
            layers.forEach(callback);
          },
        };
        if (typeof ref === 'function') {
          ref(geoJsonLayer);
          return;
        }
        if (ref) {
          ref.current = geoJsonLayer;
        }
      }, [layers, ref]);

      return (
        <div data-testid="geojson-layer">
          {layers.map((layer, index) => (
            <button
              key={`${layer.feature.properties.display_key}-${index}`}
              type="button"
              data-testid={`geojson-feature-${index}`}
              onClick={() => layer._events['click']?.()}
              onMouseEnter={() => layer._events['mouseover']?.()}
              onMouseLeave={() => layer._events['mouseout']?.()}
            >
              {layer.feature.properties.display_name}
            </button>
          ))}
        </div>
      );
    }),
  };
});

jest.mock('leaflet', () => {
  const latLngBounds = jest.fn((southWest: unknown, northEast?: unknown) => ({
    extend: jest.fn(),
    getSouthWest: jest.fn(() => southWest),
    getNorthEast: jest.fn(() => northEast ?? southWest),
  }));

  return {
    __esModule: true,
    default: {
      latLngBounds,
    },
    latLngBounds,
  };
});

function makeFeature(
  id: string,
  displayKey: string,
  displayName: string,
): MockFeature {
  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [[[-74, 40.7], [-73.9, 40.7], [-73.9, 40.8], [-74, 40.8], [-74, 40.7]]],
    },
    properties: {
      id,
      display_key: displayKey,
      display_name: displayName,
      borough: 'Manhattan',
      region_name: displayName,
    },
  };
}

function installMatchMedia(matches: boolean) {
  prefersDarkMode = matches;
  mediaQueryListeners.clear();
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: jest.fn().mockImplementation(() => ({
      matches: prefersDarkMode,
      media: '(prefers-color-scheme: dark)',
      onchange: null,
      addEventListener: (_event: string, listener: (event: MediaQueryListEvent) => void) => {
        mediaQueryListeners.add(listener);
      },
      removeEventListener: (_event: string, listener: (event: MediaQueryListEvent) => void) => {
        mediaQueryListeners.delete(listener);
      },
      addListener: jest.fn(),
      removeListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

describe('NeighborhoodSelectorMap', () => {
  const originalJawgToken = process.env['NEXT_PUBLIC_JAWG_TOKEN'];

  beforeEach(() => {
    jest.clearAllMocks();
    renderedLayers.splice(0, renderedLayers.length);
    currentMap = mockMap;
    tileLayerState.url = '';
    tileLayerState.onTileError = null;
    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = 'test-jawg-token';
    installMatchMedia(false);
  });

  afterAll(() => {
    if (originalJawgToken === undefined) {
      delete process.env['NEXT_PUBLIC_JAWG_TOKEN'];
      return;
    }
    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = originalJawgToken;
  });

  it('toggles consolidated neighborhoods by display_key when any polygon is clicked', async () => {
    const onToggleKey = jest.fn();
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
            makeFeature('row-2', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
            makeFeature('row-3', 'nyc-manhattan-chelsea', 'Chelsea'),
          ],
        }}
        selectedKeys={new Set()}
        onToggleKey={onToggleKey}
        hoveredKey={null}
      />,
    );

    await user.click(screen.getByTestId('geojson-feature-0'));

    expect(onToggleKey).toHaveBeenCalledWith('nyc-manhattan-upper-east-side');
  });

  it('updates hover state from polygon interactions', async () => {
    const onHoverKey = jest.fn();
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
        hoveredKey={null}
        onHoverKey={onHoverKey}
      />,
    );

    await user.hover(screen.getByTestId('geojson-feature-0'));
    await user.unhover(screen.getByTestId('geojson-feature-0'));

    expect(onHoverKey).toHaveBeenNthCalledWith(1, 'nyc-manhattan-upper-east-side');
    expect(onHoverKey).toHaveBeenNthCalledWith(2, null);
  });

  it('uses the light Jawg tiles when dark mode is not active', () => {
    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
        hoveredKey={null}
      />,
    );

    expect(screen.getByTestId('tile-layer')).toHaveAttribute(
      'data-url',
      expect.stringContaining('jawg-sunny'),
    );
  });

  it('uses the dark Jawg tiles when dark mode is active', () => {
    installMatchMedia(true);

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
        hoveredKey={null}
      />,
    );

    expect(screen.getByTestId('tile-layer')).toHaveAttribute(
      'data-url',
      expect.stringContaining('jawg-dark'),
    );
  });

  it('falls back to Carto voyager tiles after a Jawg tile error', async () => {
    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
        hoveredKey={null}
      />,
    );

    tileLayerState.onTileError?.();

    await waitFor(() => {
      expect(screen.getByTestId('tile-layer')).toHaveAttribute(
        'data-url',
        expect.stringContaining('cartocdn.com/rastertiles/voyager'),
      );
    });
  });

  it('applies selected and hovered styles across all polygons for a display key', () => {
    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
            makeFeature('row-2', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
          ],
        }}
        selectedKeys={new Set(['nyc-manhattan-upper-east-side'])}
        onToggleKey={jest.fn()}
        hoveredKey="nyc-manhattan-upper-east-side"
      />,
    );

    expect(renderedLayers).toHaveLength(2);
    for (const layer of renderedLayers) {
      expect(layer.setStyle).toHaveBeenCalled();
      expect(layer.setStyle).toHaveBeenLastCalledWith(
        expect.objectContaining({
          fill: true,
          color: '#7E22CE',
          fillColor: '#F3E8FF',
          fillOpacity: 0.6,
          weight: 3,
        }),
      );
    }
  });

  it('fits to selected polygon bounds when selected keys are present', async () => {
    const user = userEvent.setup();
    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
            makeFeature('row-2', 'nyc-manhattan-chelsea', 'Chelsea'),
          ],
        }}
        selectedKeys={new Set(['nyc-manhattan-upper-east-side', 'nyc-manhattan-chelsea'])}
        onToggleKey={jest.fn()}
        hoveredKey={null}
      />,
    );

    mockMap.fitBounds.mockClear();
    await user.click(screen.getByTestId('fit-map-button'));

    const [boundsArg, optionsArg] = mockMap.fitBounds.mock.calls[0] ?? [];
    expect(Array.isArray(boundsArg)).toBe(false);
    expect(boundsArg.extend).toHaveBeenCalled();
    expect(optionsArg).toEqual({ padding: [24, 24] });
  });

  it('falls back to default bounds when nothing is selected', async () => {
    const user = userEvent.setup();
    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
        hoveredKey={null}
      />,
    );

    mockMap.fitBounds.mockClear();
    await user.click(screen.getByTestId('fit-map-button'));

    expect(mockMap.fitBounds).toHaveBeenCalledWith(
      [
        [40.4774, -74.2591],
        [40.9176, -73.7004],
      ],
      { padding: [24, 24] },
    );
  });

  it('renders without a GeoJSON layer when no feature collection is provided', async () => {
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={null}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
        hoveredKey={null}
      />,
    );

    expect(screen.queryByTestId('geojson-layer')).not.toBeInTheDocument();

    mockMap.fitBounds.mockClear();
    await user.click(screen.getByTestId('fit-map-button'));
    expect(mockMap.fitBounds).toHaveBeenCalledWith(
      [
        [40.4774, -74.2591],
        [40.9176, -73.7004],
      ],
      { padding: [24, 24] },
    );
  });

  it('skips toggling and tooltip binding for polygons without display metadata', async () => {
    const onToggleKey = jest.fn();
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', '', '')],
        }}
        selectedKeys={new Set()}
        onToggleKey={onToggleKey}
        hoveredKey={null}
      />,
    );

    expect(renderedLayers[0]?.bindTooltip).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('geojson-feature-0'));

    expect(onToggleKey).not.toHaveBeenCalled();
  });

  it('returns early when the map handle is unavailable', async () => {
    const user = userEvent.setup();
    currentMap = null;

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set(['nyc-manhattan-upper-east-side'])}
        onToggleKey={jest.fn()}
        hoveredKey={null}
      />,
    );

    await user.click(screen.getByTestId('fit-map-button'));

    expect(mockMap.fitBounds).not.toHaveBeenCalled();
  });
});
