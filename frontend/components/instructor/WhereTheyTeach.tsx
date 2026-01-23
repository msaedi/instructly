'use client';

import type { ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { MapPin } from 'lucide-react';

const InstructorCoverageMap = dynamic(() => import('@/components/maps/InstructorCoverageMap'), { ssr: false });

type LocationPin = {
  lat: number;
  lng: number;
  label?: string;
};

type FeatureCollection = {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    geometry?: {
      type: string;
      coordinates: unknown;
    };
    properties?: Record<string, unknown>;
  }>;
};

interface WhereTheyTeachProps {
  offersTravel: boolean;
  offersAtLocation: boolean;
  offersOnline: boolean;
  coverage?: FeatureCollection | null;
  studioPins?: LocationPin[];
}

export function WhereTheyTeach({
  offersTravel,
  offersAtLocation,
  offersOnline,
  coverage = null,
  studioPins = [],
}: WhereTheyTeachProps) {
  const hasStudios = Array.isArray(studioPins) && studioPins.length > 0;
  const effectiveOffersAtLocation = offersAtLocation && hasStudios;
  const hasLessonOptions = offersTravel || effectiveOffersAtLocation || offersOnline;
  const showMap = offersTravel || effectiveOffersAtLocation;
  const studioLabel = studioPins[0]?.label;
  const legendItems: Array<{ key: string; icon: ReactNode; label: string }> = [];
  if (offersTravel) {
    legendItems.push({
      key: 'travel',
      icon: <span role="img" aria-label="Travels to you">🚗</span>,
      label: 'Travels to you',
    });
  }
  if (effectiveOffersAtLocation) {
    legendItems.push({
      key: 'studio',
      icon: <MapPin className="h-4 w-4 text-[#7E22CE]" aria-hidden="true" />,
      label: 'At studio',
    });
  }
  if (offersOnline) {
    legendItems.push({
      key: 'online',
      icon: <span role="img" aria-label="Online lessons">💻</span>,
      label: 'Online',
    });
  }

  return (
    <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Where They Teach</h2>

      {!hasLessonOptions ? (
        <div className="mt-3 text-sm text-gray-600 dark:text-gray-300">
          No lesson options configured yet.
        </div>
      ) : showMap ? (
        <>
          <div className="mt-3 overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
            <InstructorCoverageMap
              height={290}
              featureCollection={coverage || null}
              showCoverage={offersTravel}
              locationPins={studioPins}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-gray-700 dark:text-gray-200">
            {legendItems.map((item) => (
              <span key={item.key} className="flex items-center gap-1">
                {item.icon}
                <span>{item.label}</span>
              </span>
            ))}
          </div>

          {effectiveOffersAtLocation && studioLabel ? (
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Approximate studio area: {studioLabel}
            </div>
          ) : null}
        </>
      ) : (
        <div className="mt-4 flex items-center justify-center gap-2 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 py-6 text-sm text-gray-700 dark:text-gray-200">
          <span role="img" aria-label="Online lessons only">💻</span>
          <span>Online lessons only</span>
        </div>
      )}
    </section>
  );
}
