// frontend/components/InstructorCard.tsx
'use client';

import { useRouter } from 'next/navigation';
import { Star, MapPin, Heart } from 'lucide-react';
import { UserAvatar } from '@/components/user/UserAvatar';
import { Instructor, ServiceCatalogItem } from '@/types/api';
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { publicApi } from '@/features/shared/api/client';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { favoritesApi } from '@/services/api/favorites';
import { reviewsApi } from '@/services/api/reviews';
import { useSearchRatingQuery } from '@/hooks/queries/useRatings';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { getServiceAreaBoroughs, getServiceAreaDisplay } from '@/lib/profileServiceAreas';
import { at } from '@/lib/ts/safe';
import { VerifiedBadge } from '@/components/common/VerifiedBadge';

// Simple in-module cache to avoid N duplicate catalog fetches (one per card)
let catalogCache: ServiceCatalogItem[] | null = null;
let catalogPromise: Promise<ServiceCatalogItem[]> | null = null;

interface InstructorCardProps {
  instructor: Instructor;
  nextAvailableSlot?: {
    date: string;

    time: string;
    displayText: string;
  };
  onViewProfile?: () => void;
  onBookNow?: (e?: React.MouseEvent) => void;
  compact?: boolean;
}
export default function InstructorCard({
  instructor,
  nextAvailableSlot,
  onViewProfile,
  onBookNow,
  compact = false,
}: InstructorCardProps) {
  const router = useRouter();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [serviceCatalog, setServiceCatalog] = useState<ServiceCatalogItem[]>([]);
  const [isFavorited, setIsFavorited] = useState(false);
  const [isLoadingFavorite, setIsLoadingFavorite] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const primaryServiceId = instructor?.services?.[0]?.id;
  const { data: searchRating } = useSearchRatingQuery(instructor.user_id, primaryServiceId);
  const rating = typeof searchRating?.primary_rating === 'number' ? searchRating?.primary_rating : null;
  const reviewCount = searchRating?.review_count || 0;
  const [recentReviews, setRecentReviews] = useState<import('@/services/api/reviews').ReviewItem[]>([]);
  const serviceAreaBoroughs = getServiceAreaBoroughs(instructor);
  const serviceAreaDisplay = getServiceAreaDisplay(instructor) || 'NYC';
  const bgcStatusValue = (instructor as { bgc_status?: string }).bgc_status;
  const bgcCompletedAt = (instructor as { bgc_completed_at?: string | null }).bgc_completed_at ?? null;
  const backgroundCheckCompleted = Boolean((instructor as { background_check_completed?: boolean }).background_check_completed);
  const hasPassedBGC = typeof bgcStatusValue === 'string'
    ? bgcStatusValue.toLowerCase() === 'passed'
    : Boolean(backgroundCheckCompleted);
  const shouldShowVerifiedBadge = hasPassedBGC;

  // Fetch service catalog on mount with simple de-duplication
  useEffect(() => {
    const fetchServiceCatalog = async () => {
      try {
        if (catalogCache) {
          setServiceCatalog(catalogCache);
          return;
        }
        if (catalogPromise) {
          const data = await catalogPromise;
          setServiceCatalog(data);
          return;
        }
        catalogPromise = (async () => {
          const response = await publicApi.getCatalogServices();
          const data = response.data || [];
          catalogCache = data;
          return data;
        })();
        const data = await catalogPromise;
        setServiceCatalog(data);
      } catch (error) {
        logger.error('Failed to fetch service catalog', error as Error);
      }
    };
    void fetchServiceCatalog();
  }, []);

  // Check favorite status on mount if user is logged in
  useEffect(() => {
    if (user && instructor?.user_id) {
      void favoritesApi.check(instructor.user_id)
        .then(res => setIsFavorited(res.is_favorited))
        .catch(() => setIsFavorited(false));
    }
  }, [user, instructor?.user_id]);

  // (React Query handles caching and avoids duplicate fetches)

  // Fetch a couple of recent reviews to preview on the card
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const { reviews } = await reviewsApi.getRecent(instructor.user_id, undefined, 2);
        if (mounted) setRecentReviews(reviews || []);
      } catch {
        if (mounted) setRecentReviews([]);
      }
    })();
    return () => { mounted = false; };
  }, [instructor.user_id]);

  // Helper function to get service name from catalog
  const getServiceName = (serviceId: string): string => {
    const service = serviceCatalog.find((s) => s.id === serviceId);
    return service?.name || '';
  };

  // Helper function to calculate end time
  const calculateEndTime = (startTime: string, durationMinutes: number): string => {
    const parts = startTime.split(':');
    const hours = Number(at(parts, 0) || 0);
    const minutes = Number(at(parts, 1) || 0);
    const totalMinutes = hours * 60 + minutes + durationMinutes;
    const endHours = Math.floor(totalMinutes / 60);
    const endMinutes = totalMinutes % 60;
    return `${String(endHours).padStart(2, '0')}:${String(endMinutes).padStart(2, '0')}`;
  };


  const handleFavoriteClick = async () => {
    // Guest users - redirect to login
    if (!user) {
      const returnUrl = `/search?instructorToFavorite=${instructor.user_id}`;
      router.push(`/login?returnTo=${encodeURIComponent(returnUrl)}`);
      return;
    }

    if (isLoadingFavorite) return;

    // Optimistic update
    setIsFavorited(!isFavorited);
    setIsLoadingFavorite(true);

    try {
      if (isFavorited) {
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
      setIsFavorited(isFavorited);
      toast.error('Failed to update favorite');
      logger.error('Favorite toggle error', error as Error);
    } finally {
      setIsLoadingFavorite(false);
    }
  };

  // Mock bio for demo purposes - in production this should come from instructor data
  const mockBios = [
    "Juilliard graduate, patient teacher specializing in classical and pop music for all ages",
    "Berklee College graduate with 8 years experience. I specialize in jazz and contemporary music",
    "Fun and engaging lessons for all ages. Specializing in music theory and sight reading",
    "Great with kids and beginners. Making piano fun and accessible for everyone!",
    "Professional pianist with 15+ years of teaching experience. All levels welcome",
    "Conservatory-trained instructor passionate about helping students reach their potential"
  ];

  // Get a consistent bio based on instructor ID
  const getBio = () => {
    if (instructor.bio) return instructor.bio;
    const index = instructor.user_id.charCodeAt(0) % mockBios.length;
    return at(mockBios, index) || '';
  };

  return (
    <div
      className={`bg-white rounded-xl border border-gray-200 hover:shadow-lg transition-shadow relative ${
        compact ? 'px-4 py-4' : 'p-6'
      }`}
      data-testid="instructor-card"
    >
      <div className={`flex ${compact ? 'gap-4' : 'gap-6'}`}>
        {/* Left side - Profile Photo */}
        <div className="flex-shrink-0">
          {/* Profile Photo */}
          <UserAvatar
            user={{
              id: instructor.user_id,
              first_name: instructor.user.first_name,
              ...((instructor.user as { has_profile_picture?: boolean }).has_profile_picture !== undefined && {
                has_profile_picture: (instructor.user as { has_profile_picture?: boolean }).has_profile_picture
              }),
              ...((instructor.user as { profile_picture_version?: number }).profile_picture_version && {
                profile_picture_version: (instructor.user as { profile_picture_version?: number }).profile_picture_version
              }),
            }}
            size={compact ? 128 : 224}
            className={`${compact ? 'w-32 h-32' : 'w-56 h-56'}`}
          />

          {/* View and review profile link */}
          <div className={`${compact ? 'mt-2' : 'mt-3'} text-center`}>
            <button
              onClick={(e) => {
                e.preventDefault();
                onViewProfile?.();
              }}
              className={`text-[#7E22CE] hover:text-[#7E22CE] ${compact ? 'text-sm' : 'text-lg'} font-medium leading-tight cursor-pointer`}
              data-testid="instructor-link"
            >
              <div>View Profile</div>
              <div>and Reviews</div>
            </button>
          </div>
        </div>

        {/* Right side - Details */}
        <div className="flex-1">
          {/* Header row with name, price and favorite */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1">
              {/* Name with verification badge */}
              <div className="flex items-center">
                <h2 className={`${compact ? 'text-xl' : 'text-3xl'} font-extrabold text-[#7E22CE]`} data-testid="instructor-name">
                  {instructor.user.first_name} {instructor.user.last_initial ? `${instructor.user.last_initial}.` : ''}
                </h2>
                {shouldShowVerifiedBadge ? (
                  <VerifiedBadge dateISO={bgcCompletedAt} className={compact ? 'ml-2' : 'ml-3'} />
                ) : null}
              </div>

              {/* Services as pills */}
              <div className={`flex gap-2 ${compact ? 'mt-2 mb-1' : 'mt-3 mb-2'}`}>
                {instructor.services.map((service, idx) => {
                  const serviceName = getServiceName(service.service_catalog_id);
                  if (!serviceName) return null;
                  return (
                    <span
                      key={idx}
                      className={`${compact ? 'px-3 py-0.5 text-sm' : 'px-6 py-1 text-lg'} bg-gray-100 text-gray-700 rounded-full font-bold`}
                    >
                      {serviceName}
                    </span>
                  );
                })}
              </div>

              {/* Rating (show only when backend says to display) */}
              {typeof rating === 'number' && reviewCount >= 3 && (
                <div className={`flex items-center gap-1 ${compact ? 'text-sm mb-1' : 'text-lg mb-2'} text-gray-600`}>
                  <Star className={`${compact ? 'h-4 w-4' : 'h-5 w-5'} text-yellow-500 fill-current`} />
                  <span className="font-medium">{rating}</span>
                  <span>·</span>
                  <button
                    onClick={() => { router.push(`/instructors/${instructor.user_id}/reviews`); }}
                    className="underline-offset-2 hover:underline cursor-pointer"
                    aria-label="See all reviews"
                  >
                    {reviewCount} reviews
                  </button>
                </div>
              )}

              {/* Experience */}
              {!compact && (
                <p className="text-lg text-gray-600 mb-2">{instructor.years_experience} years experience</p>
              )}

              {/* Location */}
              <div className={`flex items-center ${compact ? 'text-sm mb-1' : 'text-lg mb-2'} text-gray-600`}>
                <MapPin className={`${compact ? 'h-4 w-4' : 'h-5 w-5'} mr-1`} />
                <span>{serviceAreaBoroughs.slice(0, 2).join(', ') || serviceAreaDisplay}</span>
              </div>
            </div>

            {/* Price in upper right */}
            <div className="flex items-center gap-3">
              {(() => {
                const rateRaw = instructor.services[0]?.hourly_rate as unknown;
                const rateNum = typeof rateRaw === 'number' ? rateRaw : parseFloat(String(rateRaw ?? '0'));
                const safeRate = Number.isNaN(rateNum) ? 0 : rateNum;
                return (
                  <p className={`${compact ? 'text-xl' : 'text-3xl'} font-bold text-[#7E22CE]`} data-testid="instructor-price">
                    ${safeRate}/hr
                  </p>
                );
              })()}

              {/* Favorite Button */}
              <button
                onClick={handleFavoriteClick}
                disabled={isLoadingFavorite}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
                aria-label={user ? "Toggle favorite" : "Sign in to save"}
                title={!user ? "Sign in to save this instructor" : isFavorited ? "Remove from favorites" : "Add to favorites"}
              >
                <Heart
                  className="h-5 w-5"
                  fill={isFavorited ? '#ff0000' : 'none'}
                  color={isFavorited ? '#ff0000' : '#666'}
                />
              </button>
            </div>
          </div>

          {/* Bio with 5-line limit and soft yellow background - hide in compact mode */}
          {!compact && (
          <div className="mb-3 bg-yellow-50 p-4 rounded-lg">
            <p className={`text-gray-700 italic ${!isExpanded ? 'line-clamp-5' : ''}`}>
              &quot;{getBio()}&quot;
            </p>
            {getBio().length > 400 && (
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-[#7E22CE] hover:text-[#7E22CE] text-sm font-medium mt-1 cursor-pointer"
              >
                {isExpanded ? 'Show less' : 'Read more'}
              </button>
            )}
          </div>
          )}

          {/* Session Duration Selection - Only show if instructor offers multiple durations */}
          {instructor.services?.[0]?.duration_options && instructor.services[0].duration_options.length > 1 && (
            <div className={`flex items-center gap-2 ${compact ? 'mb-2' : 'mb-4'}`}>
              <p className={`${compact ? 'text-xs' : 'text-sm'} font-medium text-gray-700`}>Duration:</p>
              <div className={`flex ${compact ? 'gap-2' : 'gap-4'}`}>
                {at(instructor.services, 0)?.duration_options?.map((duration, index) => {
                  const service = at(instructor.services, 0);
                  const rateRaw = service ? (service.hourly_rate as unknown) : 0;
                  const rateNum = typeof rateRaw === 'number' ? rateRaw : parseFloat(String(rateRaw ?? '0'));
                  const safeRate = Number.isNaN(rateNum) ? 0 : rateNum;
                  const price = service ? Math.round((safeRate * duration) / 60) : 0;
                  return (
                    <label key={duration} className="flex items-center cursor-pointer">
                      <input
                        type="radio"
                        name={`duration-${instructor.user_id}`}
                        value={duration}
                        defaultChecked={index === 0}
                        className={`${compact ? 'w-3 h-3' : 'w-4 h-4'} text-[#7E22CE] accent-purple-700 border-gray-300 focus:ring-[#7E22CE]`}
                      />
                      <span className={`ml-1 ${compact ? 'text-xs' : 'text-sm'} text-gray-700`}>{duration} min (${price})</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {/* Action Buttons - Stack vertically in compact mode */}
          <div className={`${compact ? 'flex flex-col gap-2' : 'flex gap-3'}`}>
            <button
              onClick={(e) => {
                e.preventDefault();
                if (nextAvailableSlot) {
                  // Navigate directly to booking confirmation with the next available slot
                  const bookingData = {
                    instructorId: instructor.user_id,
                    instructorName: `${instructor.user.first_name} ${instructor.user.last_initial ? `${instructor.user.last_initial}.` : ''}`,
                    lessonType: getServiceName(at(instructor.services, 0)?.service_catalog_id || '') || 'Service',
                    date: nextAvailableSlot.date,
                    startTime: nextAvailableSlot.time,
                    endTime: calculateEndTime(nextAvailableSlot.time, instructor.services[0]?.duration_options?.[0] || 60),
                    duration: instructor.services[0]?.duration_options?.[0] || 60,
                    location: '', // Leave empty to let user enter their address
                    basePrice: (() => { const r = instructor.services[0]?.hourly_rate as unknown; const n = typeof r === 'number' ? r : parseFloat(String(r ?? '0')); return Number.isNaN(n) ? 0 : n; })(),
                    serviceFee: (() => { const r = instructor.services[0]?.hourly_rate as unknown; const n = typeof r === 'number' ? r : parseFloat(String(r ?? '0')); const v = Number.isNaN(n) ? 0 : n; return Math.round(v * 0.1); })(), // 10% service fee
                    totalAmount: (() => { const r = instructor.services[0]?.hourly_rate as unknown; const n = typeof r === 'number' ? r : parseFloat(String(r ?? '0')); const v = Number.isNaN(n) ? 0 : n; return Math.round(v * 1.1); })(),
                    freeCancellationUntil: new Date(nextAvailableSlot.date),
                  };

                  // Store booking data in sessionStorage
                  sessionStorage.setItem('bookingData', JSON.stringify(bookingData));
                  sessionStorage.setItem('serviceId', instructor.services[0]?.id || '');

                  // Navigate to booking confirmation
                  router.push('/student/booking/confirm');
                }
              }}
              disabled={!nextAvailableSlot}
              className={`flex-1 text-center ${compact ? 'py-1.5 px-3 text-sm' : 'py-2.5 px-4'} rounded-lg font-medium transition-colors ${
                nextAvailableSlot
                  ? 'bg-[#7E22CE] text-white hover:bg-[#7E22CE] cursor-pointer'
                  : 'bg-gray-300 text-gray-500 cursor-not-allowed'
              }`}
            >
              {nextAvailableSlot
                ? `Next Available: ${nextAvailableSlot.displayText}`
                : 'No availability info'}
            </button>

            <button
              onClick={(e) => {
                e.preventDefault();
                onBookNow?.(e);
              }}
              className={`flex-1 text-center bg-white text-[#7E22CE] ${compact ? 'py-1.5 px-3 text-sm' : 'py-2.5 px-4'} rounded-lg font-medium border-2 border-[#7E22CE] hover:bg-purple-50 transition-colors cursor-pointer`}
            >
              More options
            </button>
          </div>

          {/* Reviews preview - show up to two real recent reviews when available (hide in compact) */}
          {!compact && recentReviews.length > 0 && (
            <div className="mt-6 grid grid-cols-2 gap-4">
              {recentReviews.map((r) => (
                <div key={r.id} className="bg-gray-50 p-3 rounded-lg">
                  <div className="flex items-center mb-1">
                    <div className="flex">
                      {[...Array(5)].map((_, i) => (
                        <Star key={i} className="h-4 w-4 text-yellow-500 fill-current" />
                      ))}
                    </div>
                  </div>
                  {r.review_text && (
                    <p className="text-sm text-gray-700 italic line-clamp-3">{`"${r.review_text}"`}</p>
                  )}
                  {r.reviewer_display_name && (
                    <p className="text-xs text-gray-500 mt-1">- {r.reviewer_display_name}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
