import { useState } from 'react';
import { Star, CheckCircle, Dumbbell, Music, Guitar, Heart } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import type { InstructorProfile } from '@/types/instructor';

interface InstructorHeaderProps {
  instructor: InstructorProfile;
}

export function InstructorHeader({ instructor }: InstructorHeaderProps) {
  const [isSaved, setIsSaved] = useState(false);

  // Get display name with privacy (FirstName L.)
  const getDisplayName = (): string => {
    if (!instructor.user) return `Instructor #${instructor.user_id}`;
    const firstName = instructor.user.first_name || '';
    const lastInitial = instructor.user.last_initial || '';
    return lastInitial ? `${firstName} ${lastInitial}.` : firstName || `Instructor #${instructor.user_id}`;
  };

  const displayName = getDisplayName();

  // Safe initials calculation from actual name fields
  const getInitials = (): string => {
    if (!instructor.user) return 'IN';
    const firstInitial = instructor.user.first_name ? instructor.user.first_name.charAt(0).toUpperCase() : '';
    const lastInitial = instructor.user.last_initial || '';
    return (firstInitial + lastInitial) || 'IN';
  };

  const initials = getInitials();

  // Mock data for ratings - replace with real data when available
  const rating = 4.9;
  const reviewCount = 127;

  // Get primary service for icon display
  const primaryService = instructor.services?.[0]?.skill?.toLowerCase() || '';

  const getServiceIcon = () => {
    if (primaryService.includes('personal training') || primaryService.includes('fitness')) {
      return <Dumbbell className="h-5 w-5" />;
    }
    if (primaryService.includes('piano')) {
      return <Music className="h-5 w-5" />;
    }
    if (primaryService.includes('guitar')) {
      return <Guitar className="h-5 w-5" />;
    }
    if (primaryService.includes('yoga')) {
      return <Heart className="h-5 w-5" />;
    }
    return null;
  };

  const formatServices = () => {
    const uniqueServices = new Set<string>();
    instructor.services?.forEach(s => {
      const baseName = s.skill?.split(' - ')[0] || s.skill;
      if (baseName) uniqueServices.add(baseName);
    });
    return Array.from(uniqueServices).slice(0, 2).join(', ');
  };

  return (
    <div className="grid grid-cols-[1fr_2fr_1fr] items-center p-6 bg-white rounded-lg border">
      {/* Left Column - Photo */}
      <div className="flex justify-start">
        <Avatar className="h-20 w-20 lg:h-24 lg:w-24">
          <AvatarFallback className="text-xl lg:text-2xl">{initials}</AvatarFallback>
        </Avatar>
      </div>

      {/* Center Column - Info */}
      <div className="flex flex-col items-center text-center space-y-2">
        {/* Name with Heart Button */}
        <div className="flex items-center gap-2">
          <h1 className="text-2xl lg:text-3xl font-bold" data-testid="instructor-profile-name">{displayName}</h1>
          <button
            onClick={() => setIsSaved(!isSaved)}
            className="ml-2 p-1 bg-transparent border-none hover:scale-110 transition-transform cursor-pointer"
            aria-label="Save instructor"
            style={{ background: 'transparent', border: 'none' }}
          >
            <Heart
              className="h-5 w-5"
              fill={isSaved ? '#ff0000' : 'none'}
              color={isSaved ? '#ff0000' : '#666'}
            />
          </button>
        </div>

        {/* Rating and Reviews */}
        <div className="flex items-center gap-2">
          <Star className="h-5 w-5 fill-yellow-400 text-yellow-400" />
          <span className="font-semibold">{rating}</span>
          <span className="text-muted-foreground">({reviewCount} reviews)</span>
        </div>

        {/* Services */}
        {formatServices() && (
          <div className="flex items-center gap-2 text-muted-foreground">
            {getServiceIcon()}
            <span>{formatServices()}</span>
          </div>
        )}

        {/* Background Check Badge */}
        {instructor.background_check_completed && (
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-600" />
            <span className="text-sm">Background Checked</span>
          </div>
        )}
      </div>

      {/* Right Column - Empty for balance */}
      <div></div>
    </div>
  );
}
