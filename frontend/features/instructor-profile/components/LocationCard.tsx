import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { MapPin, Home, Users } from 'lucide-react';
import type { InstructorProfile } from '@/types/instructor';

interface LocationCardProps {
  instructor: InstructorProfile;
}

export function LocationCard({ instructor }: LocationCardProps) {
  // Mock data for lesson locations - replace with real data when available
  const lessonLocations = [
    { type: 'home', label: "Instructor's Home" },
    { type: 'student', label: "Student's Home" },
    { type: 'online', label: 'Online Lessons' },
  ];

  const serviceAreas = instructor.areas_of_service || [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Location</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Service Areas */}
        {serviceAreas.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <MapPin className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium text-sm">Service Areas</span>
            </div>
            <div className="space-y-1 ml-6">
              {serviceAreas.map((area, idx) => (
                <div key={idx} className="text-sm text-muted-foreground">
                  {area}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Lesson Locations */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Home className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium text-sm">Lesson Locations</span>
          </div>
          <div className="space-y-1 ml-6">
            {lessonLocations.map((location, idx) => (
              <div key={idx} className="text-sm text-muted-foreground">
                {location.label}
              </div>
            ))}
          </div>
        </div>

        {/* Travel Radius - Mock */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium text-sm">Travel Radius</span>
          </div>
          <div className="text-sm text-muted-foreground ml-6">
            Up to 5 miles from home base
          </div>
        </div>

        {/* Map Preview Placeholder */}
        <div className="mt-4 pt-4 border-t">
          <div className="bg-muted rounded-lg h-32 flex items-center justify-center">
            <span className="text-xs text-muted-foreground">Map preview coming soon</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
