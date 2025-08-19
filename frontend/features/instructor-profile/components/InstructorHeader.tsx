import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Star, CheckCircle, Dumbbell, Music, Guitar, Heart } from 'lucide-react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { favoritesApi } from '@/services/api/favorites';
import { toast } from 'sonner';
import type { InstructorProfile } from '@/types/instructor';

interface InstructorHeaderProps {
  instructor: InstructorProfile;
}

export function InstructorHeader({ instructor }: InstructorHeaderProps) {
  const router = useRouter();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [isSaved, setIsSaved] = useState(instructor.is_favorited || false);
  const [favoriteCount, setFavoriteCount] = useState(instructor.favorited_count || 0);
  const [isLoading, setIsLoading] = useState(false);

  // Update favorite status and count when instructor prop changes
  useEffect(() => {
    setIsSaved(instructor.is_favorited || false);
    setFavoriteCount(instructor.favorited_count || 0);
  }, [instructor.is_favorited, instructor.favorited_count]);

  // Check favorite status on mount if user is logged in
  useEffect(() => {
    if (user && instructor?.user_id) {
      favoritesApi.check(instructor.user_id)
        .then(res => setIsSaved(res.is_favorited))
        .catch(() => setIsSaved(false));
    }
  }, [user, instructor?.user_id]);

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

  const handleHeartClick = async () => {
    // Guest users - redirect to login with return URL
    if (!user) {
      const returnUrl = `/instructors/${instructor.user_id}?action=favorite`;
      router.push(`/login?returnTo=${encodeURIComponent(returnUrl)}`);
      return;
    }

    // Prevent multiple clicks
    if (isLoading) return;

    // Optimistic update
    const newSavedState = !isSaved;
    setIsSaved(newSavedState);
    // Update the count optimistically
    setFavoriteCount(prevCount => newSavedState ? prevCount + 1 : Math.max(0, prevCount - 1));
    setIsLoading(true);

    try {
      if (isSaved) {
        await favoritesApi.remove(instructor.user_id);
        toast.success('Removed from favorites');
      } else {
        await favoritesApi.add(instructor.user_id);
        toast.success('Added to favorites!');
      }
      // Invalidate favorites list so dashboard tab reflects updates immediately
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
    } catch (error) {
      // Revert on error
      setIsSaved(isSaved);
      setFavoriteCount(instructor.favorited_count || 0);
      toast.error('Failed to update favorite');
      console.error('Favorite toggle error:', error);
    } finally {
      setIsLoading(false);
    }
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
          <div className="flex items-center gap-1">
            <button
              onClick={handleHeartClick}
              disabled={isLoading}
              className="p-1 bg-transparent border-none hover:scale-110 transition-transform cursor-pointer disabled:opacity-50"
              aria-label={user ? "Toggle favorite" : "Sign in to save"}
              title={!user ? "Sign in to save this instructor" : isSaved ? "Remove from favorites" : "Add to favorites"}
              style={{ background: 'transparent', border: 'none' }}
            >
              <Heart
                className="h-5 w-5"
                fill={isSaved ? '#ff0000' : 'none'}
                color={isSaved ? '#ff0000' : '#666'}
              />
            </button>
            {favoriteCount > 0 && (
              <span className="text-sm text-muted-foreground">
                ({favoriteCount})
              </span>
            )}
          </div>
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
