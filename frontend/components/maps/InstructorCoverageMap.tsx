'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, GeoJSON, AttributionControl, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L, { type LatLngExpression } from 'leaflet';

type FeatureCollection = {
  type: 'FeatureCollection';
  features: any[];
};

interface InstructorCoverageMapProps {
  featureCollection?: FeatureCollection | null;
  height?: number | string;
  showCoverage?: boolean;
  highlightInstructorId?: string | null;
}

function MapReadyHandler() {
  const map = useMap();
  useEffect(() => {
    console.log('Map is ready, center:', map.getCenter());
  }, [map]);
  return null;
}

export default function InstructorCoverageMap({
  featureCollection,
  height = 420,
  showCoverage = true,
  highlightInstructorId = null,
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
        whenReady={() => {
          console.log('MapContainer whenReady (no args)');
        }}
      >
        <MapReadyHandler />

        <TileLayer
          url={tileUrl}
          whenCreated={(layer) => {
            // If tiles fail to load (e.g., invalid/expired token), fall back to CartoDB
            layer.on('tileerror', () => {
              if (tileUrl !== fallbackUrl) setTileUrl(fallbackUrl);
            });
          }}
        />

        <AttributionControl position="bottomright" />

        {showCoverage && fc && fc.features?.length ? (
          <GeoJSON
            key={fc.features.length}
            data={fc}
            style={(feature: any) => {
              const serving = feature?.properties?.instructors || [];
              const highlighted = highlightInstructorId && serving.includes?.(highlightInstructorId);
              return highlighted
                ? { color: '#7c3aed', weight: 2, fillOpacity: 0.35 }
                : { color: '#7c3aed', weight: 1, fillOpacity: 0.12 };
            }}
            onEachFeature={(feature, layer) => {
              const props = (feature as any).properties || {};
              const name = props.name || props.region_id || 'Coverage Area';
              layer.bindPopup(`<div>${name}</div>`);
            }}
          />
        ) : null}

        {/* Fit map to coverage on data change */}
        {showCoverage && fc && fc.features?.length ? (
          <FitToCoverage featureCollection={fc} />
        ) : null}
      </MapContainer>
    </div>
  );
}

function FitToCoverage({ featureCollection }: { featureCollection: FeatureCollection }) {
  const map = useMap();
  useEffect(() => {
    try {
      const layer = L.geoJSON(featureCollection as any);
      const bounds = layer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds.pad(0.05));
      }
      layer.remove();
    } catch {}
  }, [featureCollection, map]);
  return null;
}
