import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Feature, Polygon } from 'geojson';
import { logger } from '@/lib/logger';

import NeighborhoodSelectorMap from '../NeighborhoodSelectorMap';

type MockFeature = Feature<
  Polygon,
  {
    id?: string;
    display_key?: string;
    display_name?: string;
    borough?: string;
    region_name?: string;
  }
>;

const mockMap = {
  fitBounds: jest.fn(),
};

let currentMap: typeof mockMap | null = mockMap;
const renderedLayers: MockLayer[] = [];
const reboundElements = new Map<string, SVGElement>();
const tileLayerState: {
  url: string;
  onTileError: (() => void) | null;
} = {
  url: '',
  onTileError: null,
};
const mediaQueryListeners = new Set<(event: MediaQueryListEvent) => void>();
let prefersDarkMode = false;
const mutableEnv = process.env as Record<string, string | undefined>;
const loggerWarnMock = logger.warn as jest.Mock;

type MockLayer = {
  feature: MockFeature;
  bindTooltip: jest.Mock;
  on?: jest.Mock;
  setStyle: jest.Mock;
  getBounds?: () => {
    extend: jest.Mock;
    getSouthWest: jest.Mock;
    getNorthEast: jest.Mock;
  };
  getElement?: () => SVGElement | null;
  _path?: SVGElement | null;
  _events: Record<string, () => void>;
};

jest.mock('react-leaflet', () => {
  const React = require('react') as typeof import('react');

  return {
    MapContainer: ({
      children,
      role,
      'aria-label': ariaLabel,
    }: {
      children: React.ReactNode;
      role?: string;
      'aria-label'?: string;
    }) => (
      <div data-testid="map-container" role={role} aria-label={ariaLabel}>
        {children}
      </div>
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
          tabIndex={-1}
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
      const elementRefs = React.useRef<Array<HTMLDivElement | null>>([]);
      const layers = data.features.map((feature, index) => {
        const events: Record<string, () => void> = {};
        const isInteractive = feature.properties.id !== 'non-interactive';
        const hasBounds = feature.properties.id !== 'no-bounds';
        const usesPathFallback =
          feature.properties.id === 'path-fallback' || feature.properties.id === 'rebind-element';
        const bounds = {
          extend: jest.fn(),
          getSouthWest: jest.fn(() => ({ lat: 40.7, lng: -74 })),
          getNorthEast: jest.fn(() => ({ lat: 40.8, lng: -73.9 })),
        };
        const layer: MockLayer = {
          feature,
          bindTooltip: jest.fn(),
          setStyle: jest.fn(),
          _events: events,
          _path: null,
          ...(isInteractive
            ? {
                on: jest.fn((eventMap: Record<string, () => void>) => {
                  Object.assign(events, eventMap);
                }),
              }
            : {}),
          ...(hasBounds ? { getBounds: () => bounds } : {}),
          ...(!usesPathFallback
            ? {
                getElement: () =>
                  (elementRefs.current[index] as unknown as SVGElement | null) ?? null,
              }
            : {}),
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

      React.useEffect(() => {
        layers.forEach((layer, index) => {
          if (layer.feature.properties.id === 'remove-before-add') {
            layer._events['remove']?.();
          }

          layer._path = (elementRefs.current[index] as unknown as SVGElement | null) ?? null;
          layer._events['add']?.();

          if (layer.feature.properties.id === 'rebind-element') {
            const reboundElement = document.createElement('div') as unknown as SVGElement;
            reboundElements.set(layer.feature.properties.id, reboundElement);
            layer._path = reboundElement;
            layer._events['add']?.();
          }
        });

        return () => {
          layers.forEach((layer) => {
            layer._events['remove']?.();
          });
        };
      }, [layers]);

      return (
        <div data-testid="geojson-layer">
          {layers.map((layer, index) => (
            <div
              key={`${layer.feature.properties.display_key}-${index}`}
              ref={(node) => {
                elementRefs.current[index] = node;
              }}
              data-testid={`geojson-feature-${index}`}
              onClick={() => layer._events['click']?.()}
              onMouseEnter={() => layer._events['mouseover']?.()}
              onMouseLeave={() => layer._events['mouseout']?.()}
            >
              {layer.feature.properties.display_name}
            </div>
          ))}
        </div>
      );
    }),
  };
});

jest.mock('@/lib/logger', () => ({
  logger: {
    warn: jest.fn(),
  },
}));

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
  displayKey?: string,
  displayName?: string,
  overrides: Partial<MockFeature['properties']> = {},
): MockFeature {
  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [[[-74, 40.7], [-73.9, 40.7], [-73.9, 40.8], [-74, 40.8], [-74, 40.7]]],
    },
    properties: {
      id,
      borough: 'Manhattan',
      region_name: displayName ?? '',
      ...(displayKey !== undefined ? { display_key: displayKey } : {}),
      ...(displayName !== undefined ? { display_name: displayName } : {}),
      ...overrides,
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
  const originalNodeEnv = process.env['NODE_ENV'];

  beforeEach(() => {
    jest.clearAllMocks();
    renderedLayers.splice(0, renderedLayers.length);
    reboundElements.clear();
    currentMap = mockMap;
    tileLayerState.url = '';
    tileLayerState.onTileError = null;
    process.env['NEXT_PUBLIC_JAWG_TOKEN'] = 'test-jawg-token';
    installMatchMedia(false);
  });

  afterAll(() => {
    if (originalNodeEnv === undefined) {
      delete mutableEnv['NODE_ENV'];
    } else {
      mutableEnv['NODE_ENV'] = originalNodeEnv;
    }
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

  it('falls back to light mode when matchMedia is unavailable', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: undefined,
    });

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
      />,
    );

    expect(screen.getByTestId('tile-layer')).toHaveAttribute(
      'data-url',
      expect.stringContaining('jawg-sunny'),
    );
  });

  it('updates Jawg tiles when the preferred color scheme changes', async () => {
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

    act(() => {
      for (const listener of mediaQueryListeners) {
        listener({ matches: true } as MediaQueryListEvent);
      }
    });

    await waitFor(() => {
      expect(screen.getByTestId('tile-layer')).toHaveAttribute(
        'data-url',
        expect.stringContaining('jawg-dark'),
      );
    });
  });

  it('uses Carto voyager tiles when no Jawg token is configured', () => {
    delete process.env['NEXT_PUBLIC_JAWG_TOKEN'];

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
      expect.stringContaining('cartocdn.com/rastertiles/voyager'),
    );
  });

  it('warns once in development when the Jawg token is missing', () => {
    mutableEnv['NODE_ENV'] = 'development';
    delete process.env['NEXT_PUBLIC_JAWG_TOKEN'];

    const { rerender } = render(
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

    rerender(
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

    expect(loggerWarnMock).toHaveBeenCalledTimes(1);
    expect(loggerWarnMock).toHaveBeenCalledWith(
      '[NeighborhoodSelectorMap] NEXT_PUBLIC_JAWG_TOKEN is not set — falling back to Carto tiles',
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

  it('applies hovered styles to unselected polygons', () => {
    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set()}
        onToggleKey={jest.fn()}
        hoveredKey="nyc-manhattan-upper-east-side"
      />,
    );

    expect(renderedLayers[0]?.setStyle).toHaveBeenLastCalledWith(
      expect.objectContaining({
        color: '#94a3b8',
        fillColor: '#e2e8f0',
        fillOpacity: 0.25,
        weight: 2,
      }),
    );
  });

  it('adds accessible map semantics and keyboard support for polygon layers', async () => {
    const onToggleKey = jest.fn();
    const onHoverKey = jest.fn();
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            makeFeature('path-fallback', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
            makeFeature('row-2', 'nyc-manhattan-chelsea', 'Chelsea'),
          ],
        }}
        selectedKeys={new Set()}
        onToggleKey={onToggleKey}
        hoveredKey={null}
        onHoverKey={onHoverKey}
      />,
    );

    expect(
      screen.getByRole('application', { name: 'Interactive neighborhood selection map' }),
    ).toBeInTheDocument();

    const firstFeature = screen.getByTestId('geojson-feature-0');
    const secondFeature = screen.getByTestId('geojson-feature-1');
    expect(firstFeature).toHaveAttribute('tabindex', '0');
    expect(firstFeature).toHaveAttribute('role', 'button');
    expect(firstFeature).toHaveAttribute('aria-label', 'Toggle Upper East Side');

    await user.tab();
    expect(firstFeature).toHaveFocus();

    await user.keyboard('{Enter}');
    await user.tab();
    expect(secondFeature).toHaveFocus();
    await user.keyboard(' ');

    expect(onToggleKey).toHaveBeenNthCalledWith(1, 'nyc-manhattan-upper-east-side');
    expect(onToggleKey).toHaveBeenNthCalledWith(2, 'nyc-manhattan-chelsea');
    expect(onHoverKey).toHaveBeenNthCalledWith(1, 'nyc-manhattan-upper-east-side');
    expect(onHoverKey).toHaveBeenNthCalledWith(2, null);
    expect(onHoverKey).toHaveBeenNthCalledWith(3, 'nyc-manhattan-chelsea');
  });

  it('rebinds keyboard listeners when Leaflet swaps the interactive element', () => {
    const onToggleKey = jest.fn();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            makeFeature('rebind-element', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
          ],
        }}
        selectedKeys={new Set()}
        onToggleKey={onToggleKey}
        hoveredKey={null}
      />,
    );

    const originalElement = screen.getByTestId('geojson-feature-0');
    const reboundElement = reboundElements.get('rebind-element');

    expect(reboundElement).toBeDefined();

    fireEvent.keyDown(originalElement, { key: 'Enter' });
    expect(onToggleKey).not.toHaveBeenCalled();

    fireEvent.keyDown(reboundElement as SVGElement, { key: 'Enter' });
    expect(onToggleKey).toHaveBeenCalledWith('nyc-manhattan-upper-east-side');
  });

  it('ignores remove events before any interactive element has been bound', async () => {
    const onToggleKey = jest.fn();
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            makeFeature('remove-before-add', 'nyc-manhattan-upper-east-side', 'Upper East Side'),
          ],
        }}
        selectedKeys={new Set()}
        onToggleKey={onToggleKey}
        hoveredKey={null}
      />,
    );

    await user.tab();
    expect(screen.getByTestId('geojson-feature-0')).toHaveFocus();

    await user.keyboard('{Enter}');
    expect(onToggleKey).toHaveBeenCalledWith('nyc-manhattan-upper-east-side');
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

  it('renders the fit-map button in a fixed overlay above Leaflet panes', () => {
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

    const fitMapButton = screen.getByTestId('fit-map-button');
    expect(fitMapButton).toHaveClass('pointer-events-auto');
    expect(fitMapButton.parentElement).toHaveClass(
      'pointer-events-none',
      'absolute',
      'inset-0',
      'z-[1100]',
      'flex',
      'items-end',
      'justify-end',
      'p-4',
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

  it('falls back to default bounds when selected polygons do not expose bounds', async () => {
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('no-bounds', 'nyc-manhattan-upper-east-side', 'Upper East Side')],
        }}
        selectedKeys={new Set(['nyc-manhattan-upper-east-side'])}
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

  it('skips toggling and tooltip binding for polygons without display metadata', async () => {
    const onToggleKey = jest.fn();
    const onHoverKey = jest.fn();
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [makeFeature('row-1')],
        }}
        selectedKeys={new Set()}
        onToggleKey={onToggleKey}
        hoveredKey={null}
        onHoverKey={onHoverKey}
      />,
    );

    expect(renderedLayers[0]?.bindTooltip).not.toHaveBeenCalled();

    await user.hover(screen.getByTestId('geojson-feature-0'));
    await user.click(screen.getByTestId('geojson-feature-0'));

    expect(onHoverKey).toHaveBeenCalledWith(null);
    expect(onToggleKey).not.toHaveBeenCalled();
  });

  it('skips event binding when a layer does not expose interaction handlers', async () => {
    const onToggleKey = jest.fn();
    const onHoverKey = jest.fn();
    const user = userEvent.setup();

    render(
      <NeighborhoodSelectorMap
        featureCollection={{
          type: 'FeatureCollection',
          features: [
            makeFeature(
              'non-interactive',
              'nyc-manhattan-upper-east-side',
              'Upper East Side',
            ),
          ],
        }}
        selectedKeys={new Set()}
        onToggleKey={onToggleKey}
        hoveredKey={null}
        onHoverKey={onHoverKey}
      />,
    );

    await user.hover(screen.getByTestId('geojson-feature-0'));
    await user.click(screen.getByTestId('geojson-feature-0'));

    expect(onHoverKey).not.toHaveBeenCalled();
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
