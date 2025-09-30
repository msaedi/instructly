import { MapPin, GraduationCap, Shield, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { InstructorProfile } from '@/types/instructor';
import { getServiceAreaBoroughs, getServiceAreaDisplay } from '@/lib/profileServiceAreas';

interface InstructorInfoProps {
  instructor: InstructorProfile;
}

export function InstructorInfo({ instructor }: InstructorInfoProps) {
  const serviceAreas = getServiceAreaBoroughs(instructor);
  const serviceAreaDisplay = getServiceAreaDisplay(instructor) || 'Location not specified';
  return (
    <div className="space-y-6">
      {/* Location */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <MapPin className="h-4 w-4" />
            Location
          </CardTitle>
        </CardHeader>
        <CardContent>
          {serviceAreas.length > 0 ? (
            <div>
              <p className="font-medium">{serviceAreaDisplay}</p>
              <p className="text-sm text-muted-foreground mt-1">
                Available for in-person lessons
              </p>
            </div>
          ) : (
            <p className="text-muted-foreground">Location not specified</p>
          )}
        </CardContent>
      </Card>

      {/* Qualifications */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <GraduationCap className="h-4 w-4" />
            Qualifications
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm">
            {instructor.years_experience > 0 && (
              <li className="flex items-start gap-2">
                <span className="text-muted-foreground">•</span>
                <span>{instructor.years_experience} years teaching experience</span>
              </li>
            )}
            {instructor.is_verified && (
              <li className="flex items-start gap-2">
                <span className="text-muted-foreground">•</span>
                <span>Identity verified</span>
              </li>
            )}
            {instructor.background_check_completed && (
              <li className="flex items-start gap-2">
                <span className="text-muted-foreground">•</span>
                <span className="flex items-center gap-1">
                  Background check verified
                  <Shield className="h-3 w-3 text-green-600" />
                </span>
              </li>
            )}
          </ul>
        </CardContent>
      </Card>

      {/* Policies */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Info className="h-4 w-4" />
            Policies
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm">
            <li className="flex items-start gap-2">
              <span className="text-muted-foreground">•</span>
              <span>Free cancellation up to 24hrs before lesson</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-muted-foreground">•</span>
              <span>First lesson satisfaction guarantee</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-muted-foreground">•</span>
              <span>In-person lessons only</span>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
