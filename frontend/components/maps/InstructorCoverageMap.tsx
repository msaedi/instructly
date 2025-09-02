'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { logger } from '@/lib/logger';
import { getString, getArray } from '@/lib/typesafe';
import { MapContainer, TileLayer, GeoJSON, AttributionControl, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L, { type LatLngExpression, type LeafletEventHandlerFnMap } from 'leaflet';

interface GeoJSONProperties {
  [key: string]: unknown;
  region?: string;
  instructor_id?: string;
  instructors_count?: number;
  instructors?: string[];
  name?: string;
  region_id?: string;
}

interface GeoJSONFeature {
  type: 'Feature';
  geometry?: {
    type: string;
    coordinates: unknown;
  } | null;
  properties?: GeoJSONProperties;
}

type FeatureCollection = {
  type: 'FeatureCollection';
  features: GeoJSONFeature[];
};

interface InstructorCoverageMapProps {
  featureCollection?: FeatureCollection | null;
  height?: number | string;
  showCoverage?: boolean;
  highlightInstructorId?: string | null;
  focusInstructorId?: string | null;
  onBoundsChange?: (bounds: L.LatLngBounds) => void;
  showSearchAreaButton?: boolean;
  onSearchArea?: () => void;
}

function MapReadyHandler() {
  const map = useMap();
  useEffect(() => {
    logger.debug('Map is ready', { center: map.getCenter() });
  }, [map]);
  return null;
}

export default function InstructorCoverageMap({
  featureCollection,
  height = 420,
  showCoverage = true,
  highlightInstructorId = null,
  focusInstructorId = null,
  onBoundsChange,
  showSearchAreaButton = false,
  onSearchArea,
}: InstructorCoverageMapProps) {
  const [fc, setFc] = useState<FeatureCollection | null>(featureCollection || null);

  useEffect(() => {
    setFc(featureCollection || null);
  }, [featureCollection]);

  const mapCenter: LatLngExpression = useMemo(
    () => [40.7831, -73.9712],
    []
  ); // Manhattan default

  // Basemap style selection (Jawg sunny/dark when token present)
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    setIsDark(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mq.addEventListener?.('change', handler);
    return () => mq.removeEventListener?.('change', handler);
  }, []);

  const jawgToken = process.env.NEXT_PUBLIC_JAWG_TOKEN;
  const primaryUrl = jawgToken
    ? isDark
      ? `https://{s}.tile.jawg.io/jawg-dark/{z}/{x}/{y}{r}.png?access-token=${jawgToken}`
      : `https://{s}.tile.jawg.io/jawg-sunny/{z}/{x}/{y}{r}.png?access-token=${jawgToken}`
    : 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
  const fallbackUrl = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
  const [tileUrl, setTileUrl] = useState<string>(primaryUrl);
  const [jawgFailed, setJawgFailed] = useState<boolean>(false);

  // Live theme switching: update tiles when theme changes, unless Jawg previously failed
  useEffect(() => {
    if (jawgToken && !jawgFailed) {
      setTileUrl(primaryUrl);
    } else if (!jawgToken) {
      setTileUrl(fallbackUrl);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDark, jawgToken, jawgFailed]);

  const containerStyle = {
    height: typeof height === 'number' ? `${height}px` : (height as string),
    width: '100%',
  } as React.CSSProperties;

  return (
    <div style={containerStyle}>
      <MapContainer
        center={mapCenter}
        zoom={12}
        style={{ height: '100%', width: '100%' }}
        attributionControl={false}
        zoomControl={false}
        whenReady={() => {
          logger.debug('MapContainer whenReady');
        }}
      >
        <MapReadyHandler />

        <TileLayer
          url={tileUrl}
          eventHandlers={{
            tileerror: () => {
              setJawgFailed(true);
              if (tileUrl !== fallbackUrl) setTileUrl(fallbackUrl);
            },
          } as LeafletEventHandlerFnMap}
        />

        <AttributionControl position="bottomleft" />

        {showCoverage && fc && fc.features?.length ? (
          <GeoJSON
            key={fc.features.length}
            data={fc}
            style={(feature) => {
              const serving = getArray(feature?.properties, 'instructors');
              const highlighted = highlightInstructorId && Array.isArray(serving) && serving.includes(highlightInstructorId);
              return highlighted
                ? { color: '#7c3aed', weight: 2, fillOpacity: 0.35 }
                : { color: '#7c3aed', weight: 1, fillOpacity: 0.12 };
            }}
            onEachFeature={(feature, layer) => {
              const props = feature.properties;
              const name = getString(props, 'name') || getString(props, 'region_id') || 'Coverage Area';
              layer.bindPopup(`<div>${name}</div>`);
            }}
          />
        ) : null}

        {/* Fit map to coverage on data change or when focusing on instructor */}
        {showCoverage && fc && fc.features?.length ? (
          <FitToCoverage featureCollection={fc} focusInstructorId={focusInstructorId} />
        ) : null}

        {/* Place custom controls top-right so they're always visible in stacked view */}
        <CustomControls />

        {/* Map bounds tracker */}
        <MapBoundsTracker onBoundsChange={onBoundsChange} />

        {/* Search this area button */}
        {showSearchAreaButton && (
          <SearchAreaButton onSearchArea={onSearchArea} />
        )}
      </MapContainer>
    </div>
  );
}

function FitToCoverage({ featureCollection, focusInstructorId }: { featureCollection: FeatureCollection; focusInstructorId?: string | null }) {
  const map = useMap();
  const [hasInitiallyFit, setHasInitiallyFit] = useState(false);

  // Initial fit to all coverage (only once)
  useEffect(() => {
    if (!hasInitiallyFit && !focusInstructorId) {
      try {
        const layer = L.geoJSON(featureCollection);
        const bounds = layer.getBounds();
        if (bounds.isValid()) {
          map.fitBounds(bounds, {
            paddingTopLeft: [20, 20],
            paddingBottomRight: [20, 60]
          });
          setHasInitiallyFit(true);
        }
        layer.remove();
      } catch {}
    }
  }, [featureCollection, map, focusInstructorId, hasInitiallyFit]);

  // Focus on specific instructor's coverage when clicked
  useEffect(() => {
    if (focusInstructorId && featureCollection) {
      try {
        // Filter features for the specific instructor
        const instructorFeatures = featureCollection.features.filter((feature) => {
          const instructors = feature.properties?.instructors || [];
          return instructors.includes(focusInstructorId);
        });

        if (instructorFeatures.length > 0) {
          const instructorFC: FeatureCollection = {
            type: 'FeatureCollection',
            features: instructorFeatures
          };
          const layer = L.geoJSON(instructorFC);
          const bounds = layer.getBounds();
          if (bounds.isValid()) {
            map.flyToBounds(bounds, {
              paddingTopLeft: [40, 40],
              paddingBottomRight: [40, 80],
              duration: 0.8
            });
          }
          layer.remove();
        }
      } catch {}
    }
  }, [focusInstructorId, featureCollection, map]);

  return null;
}

function MapBoundsTracker({ onBoundsChange }: { onBoundsChange?: (bounds: L.LatLngBounds) => void }) {
  const map = useMap();

  useEffect(() => {
    if (!onBoundsChange) return;

    const handleMoveEnd = () => {
      const bounds = map.getBounds();
      onBoundsChange(bounds);
    };

    map.on('moveend', handleMoveEnd);
    map.on('zoomend', handleMoveEnd);

    return () => {
      map.off('moveend', handleMoveEnd);
      map.off('zoomend', handleMoveEnd);
    };
  }, [map, onBoundsChange]);

  return null;
}

function SearchAreaButton({ onSearchArea }: { onSearchArea?: () => void }) {
  const map = useMap();

  useEffect(() => {
    if (!onSearchArea) return;

    const control = new L.Control({ position: 'topleft' });
    control.onAdd = () => {
      const container = L.DomUtil.create('div');
      container.style.marginTop = '10px';
      container.style.marginLeft = '10px';

      const button = document.createElement('button');
      button.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px;">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
          </svg>
          <span>Search this area</span>
        </div>
      `;
      button.style.cssText = `
        background: white;
        border: none;
        padding: 8px 16px;
        border-radius: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        color: #333;
        transition: all 0.2s;
      `;

      button.onmouseover = () => {
        button.style.boxShadow = '0 4px 12px rgba(0,0,0,0.2)';
      };
      button.onmouseout = () => {
        button.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
      };

      button.onclick = (e) => {
        e.preventDefault();
        onSearchArea();
      };

      container.appendChild(button);
      L.DomEvent.disableClickPropagation(container);
      return container;
    };

    const ctl = (control as unknown as L.Control).addTo(map);
    return () => {
      ctl.remove();
    };
  }, [map, onSearchArea]);

  return null;
}

function CustomControls() {
  const map = useMap();
  useEffect(() => {
    const control = new L.Control({ position: 'bottomright' });
    control.onAdd = () => {
      const container = L.DomUtil.create('div');
      container.style.display = 'flex';
      container.style.flexDirection = 'column';
      container.style.margin = '8px';
      container.style.zIndex = '1200';

      const panel = document.createElement('div');
      panel.style.background = '#ffffff';
      panel.style.borderRadius = '10px';
      panel.style.boxShadow = '0 3px 10px rgba(0,0,0,0.16)';
      panel.style.display = 'flex';
      panel.style.flexDirection = 'column';
      panel.style.alignItems = 'center';
      panel.style.padding = '5px';
      panel.style.zIndex = '1200';

      const btnBase: React.CSSProperties = {
        width: '24px',
        height: '24px',
        borderRadius: '6px',
        background: '#fff',
        border: '0',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 1px 2px rgba(0,0,0,0.08) inset',
      };

      const divider = () => {
        const d = document.createElement('div');
        d.style.height = '1px';
        d.style.width = '18px';
        d.style.background = 'rgba(0,0,0,0.15)';
        d.style.margin = '5px 0';
        return d;
      };

      // Locate button
      const locate = document.createElement('button');
      Object.assign(locate.style, btnBase);
      locate.title = 'Show your location';
      locate.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3"/><path d="M12 19v3"/><path d="M2 12h3"/><path d="M19 12h3"/></svg>`;
      let locationMarker: L.CircleMarker | null = null;
      let isMoving = false;
      locate.onclick = (e) => {
        e.preventDefault();
        if (!navigator.geolocation) return;
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const latlng = [pos.coords.latitude, pos.coords.longitude] as [number, number];
            // Stop ongoing animations to avoid jitter
            if ('stop' in map && typeof map.stop === 'function') {
              map.stop();
            }
            if (isMoving) return;
            isMoving = true;
            const targetZoom = Math.max(map.getZoom(), 14);
            const current = map.getCenter();
            const dx = Math.abs(current.lat - latlng[0]);
            const dy = Math.abs(current.lng - latlng[1]);
            const farMove = dx + dy > 0.002; // ~200m threshold
            const end = () => {
              isMoving = false;
              map.off('moveend', end);
              map.off('zoomend', end);
            };
            map.on('moveend', end);
            map.on('zoomend', end);
            if (farMove) {
              map.flyTo(latlng, targetZoom, { duration: 0.45, animate: true });
            } else {
              map.setView(latlng, targetZoom, { animate: false });
            }
            // Replace previous marker if exists
            if (locationMarker) {
              locationMarker.remove();
            }
            locationMarker = L.circleMarker(latlng, { radius: 4, color: '#7c3aed', fillOpacity: 0.9 });
            locationMarker.addTo(map);
          },
          () => {},
          { enableHighAccuracy: true, timeout: 8000 }
        );
      };

      const plus = document.createElement('button');
      Object.assign(plus.style, btnBase);
      plus.title = 'Zoom in';
      plus.innerHTML = '<span style="font-size:14px;font-weight:600;color:#555">+</span>';
      plus.onclick = (e) => {
        e.preventDefault();
        map.zoomIn(1);
      };

      const minus = document.createElement('button');
      Object.assign(minus.style, btnBase);
      minus.title = 'Zoom out';
      minus.innerHTML = '<span style="font-size:14px;font-weight:600;color:#555">−</span>';
      minus.onclick = (e) => {
        e.preventDefault();
        map.zoomOut(1);
      };

      panel.appendChild(locate);
      panel.appendChild(divider());
      panel.appendChild(plus);
      panel.appendChild(divider());
      panel.appendChild(minus);

      container.appendChild(panel);
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      return container;
    };
    const ctl = (control as unknown as L.Control).addTo(map);
    return () => {
      ctl.remove();
    };
  }, [map]);
  return null;
}
