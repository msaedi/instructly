'use client';

import dynamic from 'next/dynamic';

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
  const hasLessonOptions = offersTravel || offersAtLocation || offersOnline;
  const showMap = offersTravel || offersAtLocation;
  const studioLabel = studioPins[0]?.label;
  const legendItems = [
    offersTravel
      ? { key: 'travel', icon: '🚗', label: 'Travels to you', aria: 'Travels to you' }
      : null,
    offersAtLocation
      ? { key: 'studio', icon: '📍', label: 'At studio', aria: 'At studio' }
      : null,
    offersOnline
      ? { key: 'online', icon: '💻', label: 'Online', aria: 'Online lessons' }
      : null,
  ].filter((item): item is { key: string; icon: string; label: string; aria: string } => item !== null);

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
                <span role="img" aria-label={item.aria}>{item.icon}</span>
                <span>{item.label}</span>
              </span>
            ))}
          </div>

          {offersAtLocation && studioLabel ? (
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
