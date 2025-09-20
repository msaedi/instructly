import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Star, CheckCircle, Heart, Share2 } from 'lucide-react';
import { UserAvatar } from '@/components/user/UserAvatar';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { favoritesApi } from '@/services/api/favorites';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
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
  const [shareCopied, setShareCopied] = useState(false);
  const handleShare = async () => {
    try {
      const url = typeof window !== 'undefined' ? window.location.href : '';
      const nav = navigator as unknown as { share?: (data: { title: string; url: string }) => Promise<void> };
      if (nav.share) {
        await nav.share({ title: displayName, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 1500);
    } catch {}
  };

  const { data: ratingsData } = useInstructorRatingsQuery(instructor.user_id);
  const reviewCount = ratingsData?.overall?.total_reviews;
  const rating = (reviewCount ?? 0) >= 3 ? ratingsData?.overall?.rating : undefined;



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
      await queryClient.invalidateQueries({ queryKey: ['favorites'] });
    } catch (error) {
      // Revert on error
      setIsSaved(isSaved);
      setFavoriteCount(instructor.favorited_count || 0);
      toast.error('Failed to update favorite');
      logger.error('Favorite toggle error', error as Error);
    } finally {
      setIsLoading(false);
    }
  };


  const avatarUser = {
    id: String(instructor.user_id),
    first_name: instructor.user?.first_name,
    // last_name not present in InstructorProfile.user typing; omitted for privacy
    has_profile_picture: (instructor as unknown as { has_profile_picture?: boolean; user?: { has_profile_picture?: boolean } }).user?.has_profile_picture ?? (instructor as unknown as { has_profile_picture?: boolean }).has_profile_picture,
    profile_picture_version: (instructor as unknown as { profile_picture_version?: number; user?: { profile_picture_version?: number } }).user?.profile_picture_version ?? (instructor as unknown as { profile_picture_version?: number }).profile_picture_version,
  } as {
    id: string;
    first_name?: string;
    has_profile_picture?: boolean;
    profile_picture_version?: number;
  };

  return (
    <div className="w-full p-6 bg-white rounded-xl border border-gray-200">
      <div className="flex gap-8">
        {/* Left section - matching Services & Pricing width */}
        <div className="flex-[1.4] max-w-lg">
          <div className="flex gap-6 items-start">
            {/* Profile Photo */}
            <div className="flex-shrink-0">
              <UserAvatar
                user={avatarUser}
                size={224}
                className="rounded-full ring-1 ring-gray-200 overflow-hidden"
                fallbackBgColor="#F3E8FF"
                fallbackTextColor="#7E22CE"
                variant="display"
              />
            </div>

            {/* Info */}
            <div className="flex-1">
              <div className="flex flex-col space-y-2">
              {/* Name with Heart Button */}
              <div className="flex items-center gap-2">
                <h1 className="text-2xl lg:text-3xl font-bold text-[#7E22CE]" data-testid="instructor-profile-name">{displayName}</h1>
                {instructor.is_verified && (
                  <CheckCircle className="h-7 w-7 text-[#7E22CE]" />
                )}
                <div className="flex items-center gap-2">
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
                  <button
                    onClick={handleShare}
                    className="inline-flex items-center justify-center w-8 h-8 rounded-full hover:bg-purple-50 transition-transform cursor-pointer hover:scale-110"
                    aria-label="Share profile"
                    title={shareCopied ? 'Link copied' : 'Share profile'}
                    style={{ background: 'transparent', border: 'none' }}
                  >
                    <Share2 className="h-5 w-5 text-[#7E22CE]" />
                  </button>
                  {favoriteCount > 0 && (
                    <span className="text-sm text-muted-foreground">
                      ({favoriteCount})
                    </span>
                  )}
                </div>
              </div>

              {/* Rating and Reviews */}
              {typeof rating === 'number' && typeof reviewCount === 'number' && (
                <div className="flex items-center gap-2">
                  <Star className="h-5 w-5 fill-yellow-400 text-yellow-400" />
                  <span className="font-semibold">{rating}</span>
                  <button
                    onClick={() => router.push(`/instructors/${instructor.user_id}/reviews`)}
                    className="text-muted-foreground underline-offset-2 hover:underline cursor-pointer"
                    aria-label="See all reviews"
                  >
                    ({reviewCount} reviews)
                  </button>
                </div>
              )}

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
          </div>
        </div>

        {/* Right section - About me aligned with Lesson Locations */}
        <div className="flex-[1]">
          <h2 className="text-lg text-gray-600 mb-4">About me:</h2>
          <p className="text-sm text-gray-700 leading-relaxed">
            {instructor.bio || `Passionate instructor with ${instructor.years_experience || 'several'} years of experience. Dedicated to helping students achieve their goals through personalized instruction.`}
          </p>
        </div>
      </div>
    </div>
  );
}
