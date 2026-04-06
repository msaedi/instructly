'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LocateFixed } from 'lucide-react';
import { AttributionControl, GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';
import type {
  LatLngBoundsExpression,
  LeafletEventHandlerFnMap,
  PathOptions,
} from 'leaflet';
import L from 'leaflet';
import type { Feature as GeoJsonFeature, Geometry } from 'geojson';
import 'leaflet/dist/leaflet.css';

import { logger } from '@/lib/logger';

import type {
  NeighborhoodPolygonFeature,
  NeighborhoodPolygonFeatureCollection,
} from './types';

const DEFAULT_CENTER: [number, number] = [40.7831, -73.9712];
const DEFAULT_ZOOM = 10;
const DEFAULT_BOUNDS: LatLngBoundsExpression = [
  [40.4774, -74.2591],
  [40.9176, -73.7004],
];

type NeighborhoodSelectorMapProps = {
  featureCollection: NeighborhoodPolygonFeatureCollection | null;
  selectedKeys: Set<string>;
  onToggleKey: (key: string) => void;
  hoveredKey?: string | null;
  onHoverKey?: (key: string | null) => void;
  className?: string;
};

function getPolygonStyle(
  displayKey: string | undefined,
  selectedKeys: Set<string>,
  hoveredKey: string | null,
): PathOptions {
  const isSelected = Boolean(displayKey && selectedKeys.has(displayKey));
  const isHovered = Boolean(displayKey && hoveredKey === displayKey);

  if (isSelected) {
    return {
      fill: true,
      color: '#7E22CE',
      fillColor: '#F3E8FF',
      fillOpacity: isHovered ? 0.6 : 0.4,
      weight: isHovered ? 3 : 2,
    };
  }

  return {
    fill: true,
    color: '#94a3b8',
    fillColor: isHovered ? '#e2e8f0' : '#f1f5f9',
    fillOpacity: isHovered ? 0.25 : 0.15,
    weight: isHovered ? 2 : 1,
  };
}

function MapHandleBridge({
  onReady,
}: {
  onReady: (map: L.Map) => void;
}) {
  const map = useMap();

  useEffect(() => {
    onReady(map);
  }, [map, onReady]);

  return null;
}

export default function NeighborhoodSelectorMap({
  featureCollection,
  selectedKeys,
  onToggleKey,
  hoveredKey = null,
  onHoverKey,
  className,
}: NeighborhoodSelectorMapProps) {
  const mapRef = useRef<L.Map | null>(null);
  const geoJsonRef = useRef<L.GeoJSON<Geometry> | null>(null);
  const layersByKey = useRef<Map<string, L.Path[]>>(new Map());
  const boundsByKey = useRef<Map<string, L.LatLngBounds>>(new Map());
  const hasInitialFit = useRef(false);
  const hasWarnedMissingJawgToken = useRef(false);
  const [isDark, setIsDark] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return false;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const [jawgFailed, setJawgFailed] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return;
    }
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleThemeChange = (event: MediaQueryListEvent) => {
      setIsDark(event.matches);
    };
    mediaQuery.addEventListener?.('change', handleThemeChange);
    return () => {
      mediaQuery.removeEventListener?.('change', handleThemeChange);
    };
  }, []);

  const jawgToken = process.env['NEXT_PUBLIC_JAWG_TOKEN'];
  useEffect(() => {
    if (
      jawgToken ||
      process.env.NODE_ENV !== 'development' ||
      hasWarnedMissingJawgToken.current
    ) {
      return;
    }
    hasWarnedMissingJawgToken.current = true;
    logger.warn(
      '[NeighborhoodSelectorMap] NEXT_PUBLIC_JAWG_TOKEN is not set — falling back to Carto tiles',
    );
  }, [jawgToken]);

  const primaryTileUrl = useMemo(
    () =>
      jawgToken
        ? isDark
          ? `https://{s}.tile.jawg.io/jawg-dark/{z}/{x}/{y}{r}.png?access-token=${jawgToken}`
          : `https://{s}.tile.jawg.io/jawg-sunny/{z}/{x}/{y}{r}.png?access-token=${jawgToken}`
        : 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    [isDark, jawgToken],
  );
  const fallbackTileUrl =
    'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
  const tileUrl = jawgToken && !jawgFailed ? primaryTileUrl : fallbackTileUrl;

  const applyStyles = useCallback(() => {
    layersByKey.current.forEach((layers, key) => {
      const style = getPolygonStyle(key, selectedKeys, hoveredKey);
      for (const layer of layers) {
        layer.setStyle(style);
      }
    });
  }, [hoveredKey, selectedKeys]);

  const indexLayers = useCallback(() => {
    const geoJsonLayer: L.GeoJSON<Geometry> | null = geoJsonRef.current;
    if (!geoJsonLayer) {
      layersByKey.current = new Map();
      boundsByKey.current = new Map();
      return;
    }

    const nextLayers = new Map<string, L.Path[]>();
    const nextBounds = new Map<string, L.LatLngBounds>();

    geoJsonLayer.eachLayer((layer) => {
      const keyedLayer = layer as L.Layer & {
        feature?: NeighborhoodPolygonFeature;
        setStyle?: (style: PathOptions) => void;
        getBounds?: () => L.LatLngBounds;
      };
      const displayKey = keyedLayer.feature?.properties?.display_key;
      if (!displayKey || typeof keyedLayer.setStyle !== 'function') {
        return;
      }

      const existingLayers = nextLayers.get(displayKey) ?? [];
      existingLayers.push(keyedLayer as unknown as L.Path);
      nextLayers.set(displayKey, existingLayers);

      if (typeof keyedLayer.getBounds === 'function') {
        const layerBounds = keyedLayer.getBounds();
        const existingBounds = nextBounds.get(displayKey);
        if (existingBounds) {
          existingBounds.extend(layerBounds);
        } else {
          nextBounds.set(displayKey, layerBounds);
        }
      }
    });

    layersByKey.current = nextLayers;
    boundsByKey.current = nextBounds;
  }, []);

  useEffect(() => {
    indexLayers();
  }, [featureCollection, indexLayers]);

  useEffect(() => {
    applyStyles();
  }, [applyStyles]);

  const fitMap = useCallback(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    const selectedBounds = Array.from(selectedKeys)
      .map((key) => boundsByKey.current.get(key))
      .filter((bounds): bounds is L.LatLngBounds => Boolean(bounds));

    const [firstBounds, ...remainingBounds] = selectedBounds;
    if (firstBounds) {
      const union = L.latLngBounds(
        firstBounds.getSouthWest(),
        firstBounds.getNorthEast(),
      );
      for (const bounds of remainingBounds) {
        union.extend(bounds);
      }
      map.fitBounds(union, { padding: [24, 24] });
      return;
    }

    map.fitBounds(DEFAULT_BOUNDS, { padding: [24, 24] });
  }, [selectedKeys]);

  useEffect(() => {
    if (!mapRef.current || hasInitialFit.current) {
      return;
    }
    hasInitialFit.current = true;
    mapRef.current.fitBounds(DEFAULT_BOUNDS, { padding: [24, 24] });
  }, [featureCollection]);

  const handleFeature = useCallback(
    (feature: NeighborhoodPolygonFeature, layer: L.Layer) => {
      const displayKey = feature.properties?.display_key;
      const displayName = feature.properties?.display_name ?? '';
      const interactiveLayer = layer as L.Layer & {
        bindTooltip?: (content: string, options?: Record<string, unknown>) => void;
        on?: (eventMap: LeafletEventHandlerFnMap) => void;
        getElement?: () => SVGElement | null;
        _path?: SVGElement | null;
      };
      let boundElement: SVGElement | null = null;
      const handleKeyDown = (event: KeyboardEvent) => {
        if ((event.key === 'Enter' || event.key === ' ') && displayKey) {
          event.preventDefault();
          onToggleKey(displayKey);
        }
      };
      const handleFocus = () => onHoverKey?.(displayKey ?? null);
      const handleBlur = () => onHoverKey?.(null);
      const bindInteractiveElement = () => {
        // Leaflet internal fallback: _path is not public API and may break on major version upgrade.
        const element = interactiveLayer.getElement?.() ?? interactiveLayer._path ?? null;
        if (!element) {
          return;
        }
        element.setAttribute('tabindex', '0');
        element.setAttribute('role', 'button');
        element.setAttribute(
          'aria-label',
          displayName ? `Toggle ${displayName}` : 'Toggle neighborhood',
        );
        if (boundElement === element) {
          return;
        }
        if (boundElement) {
          boundElement.removeEventListener('keydown', handleKeyDown);
          boundElement.removeEventListener('focus', handleFocus);
          boundElement.removeEventListener('blur', handleBlur);
        }
        boundElement = element;
        boundElement.addEventListener('keydown', handleKeyDown);
        boundElement.addEventListener('focus', handleFocus);
        boundElement.addEventListener('blur', handleBlur);
      };
      const unbindInteractiveElement = () => {
        if (!boundElement) {
          return;
        }
        boundElement.removeEventListener('keydown', handleKeyDown);
        boundElement.removeEventListener('focus', handleFocus);
        boundElement.removeEventListener('blur', handleBlur);
        boundElement = null;
      };

      if (displayName && typeof interactiveLayer.bindTooltip === 'function') {
        interactiveLayer.bindTooltip(displayName, { sticky: true, direction: 'top' });
      }

      if (typeof interactiveLayer.on === 'function') {
        interactiveLayer.on({
          add: bindInteractiveElement,
          remove: unbindInteractiveElement,
          click: () => {
            if (displayKey) {
              onToggleKey(displayKey);
            }
          },
          mouseover: () => onHoverKey?.(displayKey ?? null),
          mouseout: () => onHoverKey?.(null),
        });
      }
      bindInteractiveElement();
    },
    [onHoverKey, onToggleKey],
  );

  return (
    <div
      className={`relative h-full min-h-[400px] overflow-hidden rounded-[28px] border border-gray-200 bg-white/95 shadow-sm dark:border-gray-800 dark:bg-gray-900/80 ${className ?? ''}`}
      data-testid="neighborhood-selector-map"
      role="application"
      aria-label="Interactive neighborhood selection map"
    >
      <MapContainer
        center={DEFAULT_CENTER}
        zoom={DEFAULT_ZOOM}
        style={{ height: '100%', width: '100%' }}
        attributionControl={false}
        zoomAnimation={false}
        markerZoomAnimation={false}
        fadeAnimation={false}
      >
        <MapHandleBridge
          onReady={(map) => {
            mapRef.current = map;
          }}
        />
        <TileLayer
          url={tileUrl}
          eventHandlers={{
            tileerror: () => {
              setJawgFailed(true);
            },
          } as LeafletEventHandlerFnMap}
        />
        <AttributionControl position="bottomleft" />
        {featureCollection ? (
          <GeoJSON
            ref={(layer: L.GeoJSON<Geometry> | null) => {
              geoJsonRef.current = layer;
            }}
            data={featureCollection}
            style={(feature) =>
              getPolygonStyle(
                (feature as NeighborhoodPolygonFeature | undefined)?.properties?.display_key,
                selectedKeys,
                hoveredKey,
              )
            }
            onEachFeature={(feature: GeoJsonFeature<Geometry>, layer) =>
              handleFeature(feature as NeighborhoodPolygonFeature, layer)
            }
          />
        ) : null}
      </MapContainer>

      <button
        type="button"
        onClick={fitMap}
        className="absolute bottom-4 right-4 inline-flex cursor-pointer items-center gap-2 rounded-full border border-gray-200 bg-white/95 px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors duration-150 hover:border-purple-200 hover:text-(--color-brand-dark) dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-200"
        data-testid="fit-map-button"
      >
        <LocateFixed className="h-4 w-4" />
        Fit map
      </button>
    </div>
  );
}
