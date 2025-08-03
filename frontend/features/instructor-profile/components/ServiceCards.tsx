import { Dumbbell, Music, Guitar, Heart, Trophy, Mic, BookOpen } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import type { InstructorService } from '@/types/instructor';

interface ServiceCardsProps {
  services: InstructorService[];
  selectedSlot?: { date: string; time: string; duration: number } | null;
  onBookService?: (service: InstructorService) => void;
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

export function ServiceCards({ services, selectedSlot, onBookService }: ServiceCardsProps) {
  if (!services || services.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No services available at this time.
      </div>
    );
  }

  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-3 max-w-4xl">
      {services.slice(0, 3).map((service) => {
        const serviceDuration = service.duration_minutes || 60;
        const canBook = !selectedSlot || serviceDuration <= 60; // Assuming 60 min slots

        return (
          <Card
            key={service.id}
            className={`transition-all ${!canBook ? 'opacity-50' : 'hover:shadow-md'}`}
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
                {serviceDuration} min · ${service.hourly_rate || 0}
              </div>
              <Button
                className="w-full"
                size="sm"
                disabled={!canBook}
                onClick={() => {
                  if (onBookService && canBook) {
                    onBookService(service);
                  }
                }}
                title={!canBook ? `Requires ${serviceDuration} min slot` : ''}
              >
                Book This
              </Button>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
