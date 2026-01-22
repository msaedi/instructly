import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Star, Heart, Share2, ShieldCheck } from 'lucide-react';
import { UserAvatar } from '@/components/user/UserAvatar';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { favoritesApi } from '@/services/api/favorites';
import { useFavoriteStatus, useSetFavoriteStatus } from '@/hooks/queries/useFavoriteStatus';
import { toast } from 'sonner';
import type { InstructorProfile } from '@/types/instructor';
import { FoundingBadge } from '@/components/ui/FoundingBadge';
import { BGCBadge } from '@/components/ui/BGCBadge';

interface InstructorHeaderProps {
  instructor: InstructorProfile;
}

export function InstructorHeader({ instructor }: InstructorHeaderProps) {
  const router = useRouter();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [isLoading, setIsLoading] = useState(false);

  // Use React Query hook for favorite status (prevents duplicate API calls)
  const { data: favoriteStatus } = useFavoriteStatus(instructor.user_id, instructor.is_favorited);
  const setFavoriteStatus = useSetFavoriteStatus();
  const isSaved = favoriteStatus ?? instructor.is_favorited ?? false;

  // Get display name with privacy (FirstName L.)
  const getDisplayName = (): string => {
    if (!instructor.user) return `Instructor #${instructor.user_id}`;
    const firstName = instructor.user.first_name || '';
    const lastInitial = instructor.user.last_initial || '';
    return lastInitial ? `${firstName} ${lastInitial}.` : firstName || `Instructor #${instructor.user_id}`;
  };

  const displayName = getDisplayName();
  const bgcStatusValue = (instructor as { bgc_status?: string | null }).bgc_status;
  const bgcStatus = typeof bgcStatusValue === 'string' ? bgcStatusValue.toLowerCase() : '';
  const isLive = Boolean(instructor.is_live);
  const showBGCBadge = isLive || bgcStatus === 'pending';
  const backgroundCheckVerified = isLive || bgcStatus === 'passed';
  const isFoundingInstructor = Boolean(instructor.is_founding_instructor);
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
    setFavoriteStatus(instructor.user_id, newSavedState);
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
    } catch {
      // Revert on error
      setFavoriteStatus(instructor.user_id, isSaved);
      toast.error('Failed to update favorite');
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
        {/* Left section - matching Skills and pricing width */}
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
              {/* Name with Action Buttons */}
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-2xl lg:text-3xl font-bold text-[#7E22CE]" data-testid="instructor-profile-name">{displayName}</h1>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={handleHeartClick}
                    disabled={isLoading}
                    className="p-0.5 bg-transparent border-none hover:scale-110 transition-transform cursor-pointer disabled:opacity-50"
                    aria-label={user ? "Toggle favorite" : "Sign in to save"}
                    title={!user ? "Sign in to save this instructor" : isSaved ? "Remove from favorites" : "Add to favorites"}
                    style={{ background: 'transparent', border: 'none' }}
                  >
                    <Heart
                      className="h-5 w-5"
                      fill={isSaved ? '#7E22CE' : 'none'}
                      color="#7E22CE"
                    />
                  </button>
                  <button
                    onClick={handleShare}
                    className="inline-flex items-center justify-center w-7 h-7 rounded-full hover:bg-purple-50 transition-transform cursor-pointer hover:scale-110"
                    aria-label="Share profile"
                    title={shareCopied ? 'Link copied' : 'Share profile'}
                    style={{ background: 'transparent', border: 'none' }}
                  >
                    <Share2 className="h-5 w-5 text-[#7E22CE]" />
                  </button>
                </div>
              </div>

              {(isFoundingInstructor || showBGCBadge) && (
                <div className="flex flex-wrap items-center gap-2">
                  {isFoundingInstructor && <FoundingBadge size="md" />}
                  {showBGCBadge && <BGCBadge isLive={isLive} bgcStatus={bgcStatusValue ?? null} />}
                </div>
              )}

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
              {backgroundCheckVerified && (
                <div className="flex items-center gap-2 text-emerald-700">
                  <ShieldCheck className="h-4 w-4" />
                  <span className="text-sm">Background check cleared</span>
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
