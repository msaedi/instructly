import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { User, Globe, Award } from 'lucide-react';
import type { InstructorProfile } from '@/types/instructor';

interface AboutCardProps {
  instructor: InstructorProfile;
}

export function AboutCard({ instructor }: AboutCardProps) {
  // Mock data for languages and education - replace with real data when available
  const languages = ['English', 'Spanish'];
  const education = 'BA Music Education, NYU';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">About</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Experience */}
        {instructor.years_experience > 0 && (
          <div className="flex items-start gap-3">
            <Award className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div className="space-y-1">
              <div className="font-medium text-sm">Experience</div>
              <div className="text-sm text-muted-foreground">
                {instructor.years_experience} years teaching
              </div>
            </div>
          </div>
        )}

        {/* Languages */}
        {languages.length > 0 && (
          <div className="flex items-start gap-3">
            <Globe className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div className="space-y-1">
              <div className="font-medium text-sm">Languages</div>
              <div className="text-sm text-muted-foreground">
                {languages.join(', ')}
              </div>
            </div>
          </div>
        )}

        {/* Education */}
        {education && (
          <div className="flex items-start gap-3">
            <User className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div className="space-y-1">
              <div className="font-medium text-sm">Education</div>
              <div className="text-sm text-muted-foreground">
                {education}
              </div>
            </div>
          </div>
        )}

        {/* Bio */}
        {instructor.bio && (
          <div className="pt-2 border-t">
            <p className="text-sm text-muted-foreground leading-relaxed">
              {instructor.bio}
            </p>
          </div>
        )}

        {/* Badges */}
        <div className="flex flex-wrap gap-2 pt-2">
          {instructor.is_verified && (
            <Badge variant="secondary" className="text-xs">
              Verified
            </Badge>
          )}
          {instructor.background_check_completed && (
            <Badge variant="secondary" className="text-xs">
              Background Check
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
