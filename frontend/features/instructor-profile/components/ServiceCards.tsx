import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { Layers, MonitorSmartphone } from 'lucide-react';
import type { InstructorService } from '@/types/instructor';

interface ServiceCardsProps {
  services: InstructorService[];
  selectedSlot?: { date: string; time: string; duration: number; availableDuration?: number } | null;
  onBookService?: (service: InstructorService, duration: number) => void;
  searchedService?: string; // To prioritize searched service
}


// Individual service card with tooltip
interface ServiceCardItemProps {
  service: InstructorService;
  duration: number;
  canBook: boolean;
  selectedSlot?: { date: string; time: string; duration: number; availableDuration?: number } | null;
  onBook: (duration: number) => void;
}

function ServiceCardItem({ service, duration, canBook, selectedSlot, onBook }: ServiceCardItemProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [selectedDuration, setSelectedDuration] = useState(duration);

  // Create a unique ID for this card instance
  const cardId = `${service.id}-${Date.now()}-${Math.random()}`;

  // Get all duration options for this service
  const durationOptions = Array.isArray(service.duration_options) && service.duration_options.length > 0
    ? service.duration_options.filter(d => typeof d === 'number' && d > 0)
    : [60];

  const rawLevels = (service as unknown as Record<string, unknown>)?.['levels_taught'];
  const levelsTaught = Array.isArray(rawLevels)
    ? rawLevels
        .map((level) => (typeof level === 'string' ? level.trim().toLowerCase() : ''))
        .filter((level) => level.length > 0)
    : Array.isArray(service.levels_taught)
      ? service.levels_taught
          .map((level) => (typeof level === 'string' ? level.trim().toLowerCase() : ''))
          .filter((level) => level.length > 0)
      : [];

  const levelLabel = (() => {
    if (!levelsTaught.length) return '';
    const uniqueLevels = Array.from(new Set(levelsTaught));
    const capitalized = uniqueLevels.map((level) => level.charAt(0).toUpperCase() + level.slice(1));
    return capitalized.join(' · ');
  })();

  const rawLocations = (service as unknown as Record<string, unknown>)?.['location_types'];
  const locationTypes = Array.isArray(rawLocations)
    ? rawLocations
        .map((loc) => (typeof loc === 'string' ? loc.trim().toLowerCase() : ''))
        .filter((loc) => loc.length > 0)
    : Array.isArray(service.location_types)
      ? service.location_types
          .map((loc) => (typeof loc === 'string' ? loc.trim().toLowerCase() : ''))
          .filter((loc) => loc.length > 0)
      : [];

  const locationLabel = (() => {
    if (!locationTypes.length) return '';
    const uniqueTypes = Array.from(new Set(locationTypes));
    const formatted = uniqueTypes.map((loc) => {
      if (loc.includes('-')) {
        return loc
          .split('-')
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join('-');
      }
      return loc.charAt(0).toUpperCase() + loc.slice(1);
    });
    return formatted.join(' · ');
  })();

  const rawAgeGroups = (service as unknown as Record<string, unknown>)?.['age_groups'];
  const ageGroups = Array.isArray(rawAgeGroups)
    ? rawAgeGroups
        .map((group) => (typeof group === 'string' ? group.trim().toLowerCase() : ''))
        .filter((group) => group.length > 0)
    : Array.isArray(service.age_groups)
      ? service.age_groups
          .map((group) => (typeof group === 'string' ? group.trim().toLowerCase() : ''))
          .filter((group) => group.length > 0)
      : [];

  const showsKidsBadge = ageGroups.includes('kids');

  // Calculate price based on selected duration with safety/coercion
  // API may return hourly_rate as a string; coerce to number
  const hourlyRateRaw = (service as unknown as Record<string, unknown>)?.['hourly_rate'] as unknown;
  const hourlyRate = typeof hourlyRateRaw === 'number' ? hourlyRateRaw : parseFloat(String(hourlyRateRaw ?? '0'));
  const price = Math.round(((isNaN(hourlyRate) ? 0 : hourlyRate) * selectedDuration) / 60);
  const showHourlyPrice = durationOptions.length <= 1;

  // Generate helpful message for unavailable services
  const getUnavailableMessage = () => {
    if (!selectedSlot) return '';

    const availableMinutes = selectedSlot.availableDuration || 60;

    if (duration > availableMinutes) {
      if (availableMinutes === 60) {
        return `This ${duration}-minute session requires a ${Math.ceil(duration / 60)}-hour time block`;
      } else {
        return `Only ${availableMinutes} minutes available from ${selectedSlot.time}. This session needs ${duration} minutes.`;
      }
    }

    return 'This duration is not available at the selected time';
  };

  return (
    <div className="relative h-full">
      <Card
        className={cn(
          "transition-all bg-gradient-to-br from-purple-50 to-lavender-50 border-purple-100 flex h-full flex-col",
          !canBook ? "opacity-50" : "hover:shadow-md"
        )}
        style={{ backgroundColor: 'rgb(249, 247, 255)' }}
        onMouseEnter={() => !canBook && setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <CardHeader className="text-center pb-2">
          <CardTitle className="text-lg">
            {service.skill || 'Service'}
          </CardTitle>
          <div className="mt-3 flex w-full flex-col items-center gap-2">
            <div className="flex w-full min-h-[26px] items-center justify-center">
              {showsKidsBadge ? (
                <span className="inline-flex items-center text-xs font-semibold px-2 py-1 rounded-full bg-yellow-100 text-gray-700">
                  Kids lesson available
                </span>
              ) : (
                <span className="text-xs opacity-0">Kids lesson available</span>
              )}
            </div>
            <div className="flex w-full flex-col items-center text-center gap-2">
              {levelLabel ? (
                <div className="flex items-center justify-center gap-2 text-xs text-gray-700 leading-tight">
                  <Layers className="h-3.5 w-3.5 text-[#7E22CE]" aria-hidden="true" />
                  <span>Levels: {levelLabel}</span>
                </div>
              ) : (
                <span className="text-xs opacity-0">Levels placeholder</span>
              )}
              {levelLabel && locationLabel ? (
                <div className="w-10/12 h-px bg-gradient-to-r from-transparent via-[#7E22CE]/40 to-transparent" />
              ) : null}
              {locationLabel ? (
                <div className="flex items-center justify-center gap-2 text-sm text-gray-700 leading-tight">
                  <MonitorSmartphone className="h-3.5 w-3.5 text-[#7E22CE]" aria-hidden="true" />
                  <span>Format: {locationLabel}</span>
                </div>
              ) : (
                <span className="text-xs opacity-0">Format placeholder</span>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex-1 flex flex-col gap-3">
          <div className="flex flex-col items-center gap-2.5 justify-center min-h-[100px]">
            <div className="min-h-[28px] flex items-center justify-center w-full">
              {durationOptions.length > 1 ? (
                <div className="flex gap-2 justify-center flex-wrap">
                  {durationOptions.map((dur) => (
                    <label
                      key={dur}
                      className="flex items-center cursor-pointer"
                    >
                      <input
                        type="radio"
                        name={`duration-${cardId}`}
                        value={dur}
                        checked={selectedDuration === dur}
                        onChange={() => setSelectedDuration(dur)}
                        className="w-3 h-3 text-[#7E22CE] accent-purple-700 border-gray-300 focus:ring-[#7E22CE]"
                      />
                      <span className="ml-1 text-xs text-gray-700 whitespace-nowrap">
                        {dur}min
                      </span>
                    </label>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="text-lg font-semibold">
              {showHourlyPrice ? `$${price}/hr` : `$${price}`}
            </div>
          </div>
          <div className="mt-auto flex justify-center">
            <button
              className={`py-1.5 px-4 rounded-lg font-medium transition-colors ${
                canBook
                  ? 'bg-[#7E22CE] text-white hover:bg-[#7E22CE] cursor-pointer'
                  : 'bg-gray-300 text-gray-500 cursor-not-allowed'
              }`}
              disabled={!canBook}
              onClick={() => onBook && onBook(selectedDuration)}
              title={!canBook ? getUnavailableMessage() : ''}
              data-testid={`book-service-${(service.skill || '').toLowerCase().replace(/\s+/g, '-')}`}
            >
              Book now!
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Tooltip */}
      {showTooltip && !canBook && (
        <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 z-50 pointer-events-none">
          <div className="bg-gray-900 text-white text-xs rounded-lg py-2 px-3 max-w-xs shadow-lg">
            <div className="whitespace-normal text-center">
              {getUnavailableMessage()}
            </div>
            {/* Arrow */}
            <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
              <div className="w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900"></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ServiceCards({ services, selectedSlot, onBookService, searchedService }: ServiceCardsProps) {
  if (!services || services.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No services available at this time.
      </div>
    );
  }

  // Create one card per service (with duration selector inside)
  const serviceCards = services.map(service => {
    // Get the default duration (first available option)
    const defaultDuration = Array.isArray(service.duration_options) && service.duration_options.length > 0
      ? service.duration_options[0]!
      : 60;

    return { service, duration: defaultDuration };
  });

  // Sort to prioritize searched service if provided
  if (searchedService) {
    serviceCards.sort((a, b) => {
      const aMatches = a.service.skill?.toLowerCase().includes(searchedService.toLowerCase()) ? 1 : 0;
      const bMatches = b.service.skill?.toLowerCase().includes(searchedService.toLowerCase()) ? 1 : 0;
      return bMatches - aMatches;
    });
  }

  // Take up to 4 service cards
  const displayedServices = serviceCards.slice(0, 4);

  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-2 items-stretch">
      {displayedServices.map((item, index) => {
        const { service, duration } = item;

        // Check if service can be booked based on available duration
        const availableMinutes = selectedSlot?.availableDuration || 120; // Default to 2 hours if no slot selected
        const canBook = !selectedSlot || duration <= availableMinutes;

        return (
          <ServiceCardItem
            key={`${service.id}-${index}`}
            service={service}
            duration={duration}
            canBook={canBook}
            {...(selectedSlot && { selectedSlot })}
            onBook={(selectedDuration) => {
              if (onBookService && canBook) {
                onBookService(service, selectedDuration);
              }
            }}
          />
        );
      })}
    </div>
  );
}
