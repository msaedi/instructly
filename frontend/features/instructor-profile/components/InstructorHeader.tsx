import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Star, CheckCircle, Dumbbell, Music, Guitar, Heart } from 'lucide-react';
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
    <div className="flex gap-6 items-start p-6 bg-white rounded-xl border border-gray-200">
      {/* Left side - Profile Photo */}
      <div className="flex-shrink-0">
        <div className="w-56 h-56 bg-gray-200 rounded-full flex items-center justify-center text-gray-500">
          <span className="text-7xl">👤</span>
        </div>
      </div>

      {/* Right side - Info */}
      <div className="flex-1">
        <div className="flex flex-col space-y-2">
        {/* Name with Heart Button */}
        <div className="flex items-center gap-2">
          <h1 className="text-2xl lg:text-3xl font-bold text-purple-700" data-testid="instructor-profile-name">{displayName}</h1>
          {instructor.is_verified && (
            <CheckCircle className="h-7 w-7 text-purple-700" />
          )}
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

        {/* Experience */}
        {instructor.years_experience && (
          <p className="text-lg text-gray-600">{instructor.years_experience} years experience</p>
        )}

        {/* Background Check Badge */}
        {instructor.background_check_completed && (
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-green-600" />
            <span className="text-sm">Background Checked</span>
          </div>
        )}
        </div>
      </div>

      {/* Right Column - Bio */}
      <div className="flex-shrink-0 max-w-md">
        <p className="text-sm text-gray-600 leading-relaxed">
          {instructor.bio || `Passionate instructor with ${instructor.years_experience || 'several'} years of experience. Dedicated to helping students achieve their goals through personalized instruction.`}
        </p>
      </div>
    </div>
  );
}
