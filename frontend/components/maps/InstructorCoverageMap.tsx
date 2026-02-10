'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
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

type LocationPin = {
  lat: number;
  lng: number;
  label?: string;
  instructorId?: string;
};

interface InstructorCoverageMapProps {
  featureCollection?: FeatureCollection | null;
  height?: number | string;
  showCoverage?: boolean;
  highlightInstructorId?: string | null;
  focusInstructorId?: string | null;
  locationPins?: LocationPin[];
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

function MapLifecycleGuard() {
  const map = useMap();

  useEffect(() => {
    return () => {
      // Guard against Leaflet transition callbacks firing after unmount.
      try {
        map.stop();
      } catch {
        // no-op
      }
    };
  }, [map]);

  return null;
}

export default function InstructorCoverageMap({
  featureCollection,
  height = 420,
  showCoverage = true,
  highlightInstructorId = null,
  focusInstructorId = null,
  locationPins = [],
  onBoundsChange,
  showSearchAreaButton = false,
  onSearchArea,
}: InstructorCoverageMapProps) {
  const fc = featureCollection ?? null;

  const mapCenter: LatLngExpression = useMemo(
    () => [40.7831, -73.9712],
    []
  ); // Manhattan default

  // Basemap style selection (Jawg sunny/dark when token present)
  const [isDark, setIsDark] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mq.addEventListener?.('change', handler);
    return () => mq.removeEventListener?.('change', handler);
  }, []);

  const jawgToken = process.env['NEXT_PUBLIC_JAWG_TOKEN'];
  const primaryUrl = jawgToken
    ? isDark
      ? `https://{s}.tile.jawg.io/jawg-dark/{z}/{x}/{y}{r}.png?access-token=${jawgToken}`
      : `https://{s}.tile.jawg.io/jawg-sunny/{z}/{x}/{y}{r}.png?access-token=${jawgToken}`
    : 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
  const fallbackUrl = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
  const [jawgFailed, setJawgFailed] = useState<boolean>(false);
  const tileUrl = jawgToken && !jawgFailed ? primaryUrl : fallbackUrl;

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
        zoomAnimation={false}
        markerZoomAnimation={false}
        fadeAnimation={false}
        whenReady={() => {
          logger.debug('MapContainer whenReady');
        }}
      >
        <MapReadyHandler />
        <MapLifecycleGuard />

        <TileLayer
          url={tileUrl}
          eventHandlers={{
            tileerror: () => {
              setJawgFailed(true);
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
                ? { color: '#7E22CE', weight: 2, fillOpacity: 0.35 }
                : { color: '#7E22CE', weight: 1, fillOpacity: 0.12 };
            }}
            onEachFeature={(feature, layer) => {
              const props = feature.properties;
              const name = getString(props, 'name') || getString(props, 'region_id') || 'Coverage Area';
              layer.bindPopup(`<div>${name}</div>`);
            }}
          />
        ) : null}

        {/* Fit map to coverage on data change or when focusing on instructor */}
        {(showCoverage && fc && fc.features?.length) || (locationPins && locationPins.length) ? (
          <FitToCoverage
            featureCollection={showCoverage ? fc : null}
            focusInstructorId={focusInstructorId}
            locationPins={locationPins}
          />
        ) : null}

        {locationPins && locationPins.length ? <MapPins locations={locationPins} /> : null}

        {/* Place custom controls top-right so they're always visible in stacked view */}
        <CustomControls />

        {/* Map bounds tracker */}
        <MapBoundsTracker {...(onBoundsChange && { onBoundsChange })} />

        {/* Search this area button */}
        {showSearchAreaButton && (
          <SearchAreaButton {...(onSearchArea && { onSearchArea })} />
        )}
      </MapContainer>
    </div>
  );
}

function FitToCoverage({
  featureCollection,
  focusInstructorId,
  locationPins,
}: {
  featureCollection?: FeatureCollection | null;
  focusInstructorId?: string | null;
  locationPins?: LocationPin[];
}) {
  const map = useMap();
  const hasCoverageFitRef = useRef(false);
  const hasPinsFitRef = useRef(false);
  const lastDataKeyRef = useRef<string | null>(null);

  const dataKey = useMemo(() => {
    const coverageIds = new Set<string>();
    if (featureCollection?.features?.length) {
      for (const feature of featureCollection.features) {
        const instructors = Array.isArray(feature.properties?.instructors)
          ? feature.properties?.instructors
          : [];
        for (const id of instructors) {
          if (typeof id === 'string' && id) coverageIds.add(id);
        }
      }
    }

    const pinIds = new Set<string>();
    if (Array.isArray(locationPins)) {
      for (const pin of locationPins) {
        if (pin.instructorId) pinIds.add(pin.instructorId);
      }
    }

    const coverageKey = Array.from(coverageIds).sort().join(',');
    const pinKey = Array.from(pinIds).sort().join(',');
    return `c:${coverageKey}|p:${pinKey}`;
  }, [featureCollection, locationPins]);

  useEffect(() => {
    if (lastDataKeyRef.current !== dataKey) {
      hasCoverageFitRef.current = false;
      hasPinsFitRef.current = false;
      lastDataKeyRef.current = dataKey;
    }
  }, [dataKey]);

  // Initial fit to all coverage (only once)
  useEffect(() => {
    if (!focusInstructorId) {
      try {
        const hasCoverage = Boolean(featureCollection && featureCollection.features?.length);
        const hasPins = Boolean(Array.isArray(locationPins) && locationPins.length);
        if (!hasCoverage && !hasPins) return;

        const shouldFitCoverage = hasCoverage && !hasCoverageFitRef.current;
        const shouldFitPinsOnly = !hasCoverage && hasPins && !hasPinsFitRef.current;

        if (!shouldFitCoverage && !shouldFitPinsOnly) return;

        let bounds: L.LatLngBounds | null = null;
        if (hasCoverage && featureCollection) {
          const layer = L.geoJSON(featureCollection);
          const coverageBounds = layer.getBounds();
          if (coverageBounds.isValid()) {
            bounds = coverageBounds;
          }
          layer.remove();
        }
        if (hasPins && Array.isArray(locationPins)) {
          const validPins = locationPins.filter(
            (pin) => Number.isFinite(pin.lat) && Number.isFinite(pin.lng)
          );
          if (validPins.length) {
            const pinBounds = L.latLngBounds(validPins.map((pin) => [pin.lat, pin.lng]));
            bounds = bounds ? bounds.extend(pinBounds) : pinBounds;
          }
        }
        if (bounds && bounds.isValid()) {
          map.fitBounds(bounds, {
            paddingTopLeft: [20, 20],
            paddingBottomRight: [20, 60],
            animate: false,
          });
          if (hasCoverage) hasCoverageFitRef.current = true;
          if (hasPins) hasPinsFitRef.current = true;
        }
      } catch {}
    }
  }, [featureCollection, map, focusInstructorId, locationPins]);

  // Focus on specific instructor's coverage when clicked
  useEffect(() => {
    if (focusInstructorId) {
      try {
        let bounds: L.LatLngBounds | null = null;

        // Filter features for the specific instructor
        if (featureCollection && featureCollection.features?.length) {
          const instructorFeatures = featureCollection.features.filter((feature) => {
            const instructors = feature.properties?.instructors || [];
            return instructors.includes(focusInstructorId);
          });

          if (instructorFeatures.length > 0) {
            const instructorFC: FeatureCollection = {
              type: 'FeatureCollection',
              features: instructorFeatures,
            };
            const layer = L.geoJSON(instructorFC);
            const coverageBounds = layer.getBounds();
            if (coverageBounds.isValid()) {
              bounds = coverageBounds;
            }
            layer.remove();
          }
        }

        if (Array.isArray(locationPins) && locationPins.length) {
          const focusedPins = locationPins.filter(
            (pin) => pin.instructorId === focusInstructorId
          );
          if (focusedPins.length) {
            const pinBounds = L.latLngBounds(
              focusedPins.map((pin) => [pin.lat, pin.lng])
            );
            if (pinBounds.isValid()) {
              bounds = bounds ? bounds.extend(pinBounds) : pinBounds;
            }
          }
        }

        if (bounds && bounds.isValid()) {
          map.flyToBounds(bounds, {
            paddingTopLeft: [40, 40],
            paddingBottomRight: [40, 80],
            animate: false,
          });
        }
      } catch {}
    }
  }, [focusInstructorId, featureCollection, map, locationPins]);

  return null;
}

function MapPins({ locations }: { locations: LocationPin[] }) {
  const map = useMap();

  useEffect(() => {
    if (!locations || locations.length === 0) {
      return;
    }

    const pinSvg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="#7E22CE" stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2c-3.9 0-7 3.1-7 7 0 5.3 7 13 7 13s7-7.7 7-13c0-3.9-3.1-7-7-7z"/><circle cx="12" cy="9" r="2.5" fill="#ffffff" stroke="none"/></svg>';
    const icon = L.divIcon({
      html: pinSvg,
      className: 'studio-pin',
      iconSize: [28, 28],
      iconAnchor: [14, 26],
      popupAnchor: [0, -22],
    });

    const markers: L.Marker[] = [];
    locations.forEach((loc) => {
      if (!Number.isFinite(loc.lat) || !Number.isFinite(loc.lng)) return;
      const marker = L.marker([loc.lat, loc.lng], { icon });
      if (loc.label) {
        marker.bindPopup(`<div>${loc.label}</div>`);
      }
      marker.addTo(map);
      markers.push(marker);
    });

    return () => {
      markers.forEach((marker) => marker.remove());
    };
  }, [map, locations]);

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
              map.flyTo(latlng, targetZoom, { animate: false });
            } else {
              map.setView(latlng, targetZoom, { animate: false });
            }
            // Replace previous marker if exists
            if (locationMarker) {
              locationMarker.remove();
            }
            locationMarker = L.circleMarker(latlng, { radius: 4, color: '#7E22CE', fillOpacity: 0.9 });
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
