import { Dumbbell, Music, Guitar, Heart, Trophy, Mic, BookOpen } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import type { InstructorService } from '@/types/instructor';

interface ServiceCardsProps {
  services: InstructorService[];
  selectedSlot?: { date: string; time: string; duration: number; availableDuration?: number } | null;
  onBookService?: (service: InstructorService, duration: number) => void;
  searchedService?: string; // To prioritize searched service
}

// Service icon mapping using Lucide React icons
function getServiceIcon(skill: string | undefined | null) {
  if (!skill) return <BookOpen className="h-6 w-6" />;

  const lowerSkill = skill.toLowerCase();

  if (lowerSkill.includes('personal training') || lowerSkill.includes('fitness')) {
    return <Dumbbell className="h-6 w-6" />;
  }
  if (lowerSkill.includes('piano')) {
    return <Music className="h-6 w-6" />;
  }
  if (lowerSkill.includes('guitar')) {
    return <Guitar className="h-6 w-6" />;
  }
  if (lowerSkill.includes('yoga')) {
    return <Heart className="h-6 w-6" />;
  }
  if (lowerSkill.includes('basketball') || lowerSkill.includes('sports')) {
    return <Trophy className="h-6 w-6" />;
  }
  if (lowerSkill.includes('voice') || lowerSkill.includes('vocal') || lowerSkill.includes('singing')) {
    return <Mic className="h-6 w-6" />;
  }

  return <BookOpen className="h-6 w-6" />;
}

// Individual service card with tooltip
interface ServiceCardItemProps {
  service: InstructorService;
  duration: number;
  canBook: boolean;
  selectedSlot?: { date: string; time: string; duration: number; availableDuration?: number } | null;
  onBook: () => void;
}

function ServiceCardItem({ service, duration, canBook, selectedSlot, onBook }: ServiceCardItemProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  // Calculate price based on duration with safety check
  const hourlyRate = typeof service.hourly_rate === 'number' ? service.hourly_rate : 0;
  const price = Math.round((hourlyRate * duration) / 60);

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
          "transition-all",
          !canBook ? "opacity-50" : "hover:shadow-md"
        )}
        onMouseEnter={() => !canBook && setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <CardHeader className="text-center pb-3">
          <div className="flex justify-center mb-2 text-muted-foreground">
            {getServiceIcon(service.skill)}
          </div>
          <CardTitle className="text-base">
            {service.skill || 'Service'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-center">
          <div className="text-sm text-muted-foreground">
            {duration} min · ${price}
          </div>
          <Button
            className="w-full"
            size="sm"
            disabled={!canBook}
            onClick={onBook}
            title={!canBook ? getUnavailableMessage() : ''}
            data-testid={`book-service-${(service.skill || '').toLowerCase().replace(/\s+/g, '-')}`}
          >
            Book This
          </Button>
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

  // Create flattened service/duration combinations
  const serviceDurationCombos: Array<{ service: InstructorService; duration: number }> = [];

  services.forEach(service => {
    // Ensure we have valid duration options
    const durations = Array.isArray(service.duration_options) && service.duration_options.length > 0
      ? service.duration_options
      : [60]; // Default to 60 minutes if no duration options

    durations.forEach(duration => {
      if (typeof duration === 'number' && duration > 0) {
        serviceDurationCombos.push({ service, duration });
      }
    });
  });

  // Sort to prioritize searched service if provided
  if (searchedService) {
    serviceDurationCombos.sort((a, b) => {
      const aMatches = a.service.skill?.toLowerCase().includes(searchedService.toLowerCase()) ? 1 : 0;
      const bMatches = b.service.skill?.toLowerCase().includes(searchedService.toLowerCase()) ? 1 : 0;
      return bMatches - aMatches;
    });
  }

  // Take up to 4 combinations
  const displayCombos = serviceDurationCombos.slice(0, 4);

  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-4 max-w-5xl">
      {displayCombos.map((combo, index) => {
        const { service, duration } = combo;

        // Check if service can be booked based on available duration
        const availableMinutes = selectedSlot?.availableDuration || 120; // Default to 2 hours if no slot selected
        const canBook = !selectedSlot || duration <= availableMinutes;

        return (
          <ServiceCardItem
            key={`${service.id}-${duration}-${index}`}
            service={service}
            duration={duration}
            canBook={canBook}
            selectedSlot={selectedSlot}
            onBook={() => {
              if (onBookService && canBook) {
                onBookService(service, duration);
              }
            }}
          />
        );
      })}
    </div>
  );
}
