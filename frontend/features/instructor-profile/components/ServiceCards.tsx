import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useState } from 'react';
import { cn } from '@/lib/utils';
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

  // Calculate price based on selected duration with safety/coercion
  // API may return hourly_rate as a string; coerce to number
  const hourlyRateRaw = (service as unknown as Record<string, unknown>)?.hourly_rate as unknown;
  const hourlyRate = typeof hourlyRateRaw === 'number' ? hourlyRateRaw : parseFloat(String(hourlyRateRaw ?? '0'));
  const price = Math.round(((isNaN(hourlyRate) ? 0 : hourlyRate) * selectedDuration) / 60);

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
    <div className="relative">
      <Card
        className={cn(
          "transition-all bg-gradient-to-br from-purple-50 to-lavender-50 border-purple-100",
          !canBook ? "opacity-50" : "hover:shadow-md"
        )}
        style={{ backgroundColor: 'rgb(249, 247, 255)' }}
        onMouseEnter={() => !canBook && setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <CardHeader className="text-center pb-3">
          <CardTitle className="text-lg">
            {service.skill || 'Service'}
          </CardTitle>
          <div className="mt-2">
            <span className="inline-block bg-yellow-100 text-yellow-800 text-xs font-medium px-2 py-1 rounded-full">
              Kids lesson available
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Duration selector with inline radio buttons like calendar */}
          {durationOptions.length > 1 ? (
            <div>
              <div className="flex gap-2 justify-center">
                {durationOptions.map((dur) => {
                  return (
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
                        className="w-3 h-3 text-[#6A0DAD] accent-purple-700 border-gray-300 focus:ring-[#6A0DAD]"
                      />
                      <span className="ml-1 text-xs text-gray-700 whitespace-nowrap">
                        {dur}min
                      </span>
                    </label>
                  );
                })}
              </div>
              <div className="text-center mt-2">
                <div className="text-lg font-semibold">${price}</div>
              </div>
            </div>
          ) : (
            <div className="text-center space-y-2">
              <div className="text-lg font-semibold">
                ${price}
              </div>
            </div>
          )}
          <div className="flex justify-center">
            <button
              className={`py-1.5 px-4 rounded-lg font-medium transition-colors ${
                canBook
                  ? 'bg-[#6A0DAD] text-white hover:bg-[#6A0DAD] cursor-pointer'
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
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-2">
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
            selectedSlot={selectedSlot}
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
