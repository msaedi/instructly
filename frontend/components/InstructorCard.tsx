// frontend/components/InstructorCard.tsx
'use client';

import { useRouter } from 'next/navigation';
import { Star, Heart, Layers, MonitorSmartphone, Clock3, MapPin } from 'lucide-react';
import { UserAvatar } from '@/components/user/UserAvatar';
import { Instructor } from '@/types/api';
import { memo, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiProblemError } from '@/lib/api/fetch';
import {
  fetchPricingPreview,
  type PricingPreviewResponse,
  formatCentsToDisplay,
} from '@/lib/api/pricing';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { favoritesApi } from '@/services/api/favorites';
import { useFavoriteStatus, useSetFavoriteStatus } from '@/hooks/queries/useFavoriteStatus';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';
import { useServicesCatalog } from '@/hooks/queries/useServices';
import { useRecentReviews } from '@/src/api/services/reviews';
import { toast } from 'sonner';
import { getServiceAreaBoroughs, getServiceAreaDisplay } from '@/lib/profileServiceAreas';
import { timeToMinutes } from '@/lib/time';
import { at } from '@/lib/ts/safe';
import { MessageInstructorButton } from '@/components/instructor/MessageInstructorButton';
import { FoundingBadge } from '@/components/ui/FoundingBadge';
import { BGCBadge } from '@/components/ui/BGCBadge';

type AvailabilitySlot = {
  start_time: string;
  end_time: string;
};

type AvailabilityDay = {
  available_slots?: AvailabilitySlot[];
  is_blackout?: boolean;
};

export interface InstructorAvailabilityData {
  timezone?: string;
  availabilityByDate: Record<string, AvailabilityDay>;
}

interface NextSlotResult {
  date: string;
  time: string;
  displayText: string;
}

const calculateEndTime = (startTime: string, durationMinutes: number): string => {
  const parts = startTime.split(':');
  const hours = Number(at(parts, 0) || 0);
  const minutes = Number(at(parts, 1) || 0);
  const totalMinutes = hours * 60 + minutes + durationMinutes;
  const endHours = Math.floor(totalMinutes / 60);
  const endMinutes = totalMinutes % 60;
  return `${String(endHours).padStart(2, '0')}:${String(endMinutes).padStart(2, '0')}`;
};

const parseIsoDateToLocal = (value: string): Date | null => {
  const parts = value.split('-');
  if (parts.length < 3) return null;
  const year = Number(parts[0]);
  const month = Number(parts[1]);
  const day = Number(parts[2]);
  if (Number.isNaN(year) || Number.isNaN(month) || Number.isNaN(day)) {
    return null;
  }
  return new Date(year, month - 1, day);
};

const parseTimeToParts = (value: string): { hour: number; minute: number } | null => {
  const parts = value.split(':');
  const hour = Number(at(parts, 0));
  const minute = Number(at(parts, 1));
  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return null;
  }
  return { hour, minute };
};

const formatDisplayText = (date: Date, hour: number, minute: number): string => {
  const dateLabel = new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }).format(date);
  const dateWithTime = new Date(date);
  dateWithTime.setHours(hour, minute, 0, 0);
  const timeLabel = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(dateWithTime);
  return `${dateLabel}, ${timeLabel}`;
};

const diffMinutes = (start: string, end: string): number => {
  const startMinutes = timeToMinutes(start);
  const endMinutes = timeToMinutes(end, { isEndTime: true });
  return endMinutes - startMinutes;
};

const toHHMM = (hour: number, minute: number): string => {
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
};

interface InstructorCardProps {
  instructor: Instructor;
  availabilityData?: InstructorAvailabilityData;
  onViewProfile?: () => void;
  onBookNow?: (e?: React.MouseEvent) => void;
  compact?: boolean;
  bookingDraftId?: string;
  appliedCreditCents?: number;
  highlightServiceCatalogId?: string;
}
function InstructorCard({
  instructor,
  availabilityData,
  onViewProfile,
  onBookNow,
  compact = false,
  bookingDraftId,
  appliedCreditCents,
  highlightServiceCatalogId,
}: InstructorCardProps) {
  const router = useRouter();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { data: serviceCatalog = [] } = useServicesCatalog();

  // Use React Query hook for favorite status (prevents duplicate API calls)
  const { data: favoriteStatus } = useFavoriteStatus(instructor.user_id);
  const setFavoriteStatus = useSetFavoriteStatus();
  const isFavorited = favoriteStatus ?? false;
  const [isLoadingFavorite, setIsLoadingFavorite] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [pricingPreview, setPricingPreview] = useState<PricingPreviewResponse | null>(null);
  const [isPricingPreviewLoading, setIsPricingPreviewLoading] = useState(false);
  const [pricingPreviewError, setPricingPreviewError] = useState<string | null>(null);
  const primaryService = instructor.services?.[0];
  const rawDurationOptions = primaryService?.duration_options;
  const durationOptions: number[] = Array.isArray(rawDurationOptions) ? rawDurationOptions : [];
  const fallbackDurationMinutes = durationOptions[0] ?? 60;
  const [selectedDuration, setSelectedDuration] = useState<number>(fallbackDurationMinutes);
  const resolvedDurationMinutes = selectedDuration ?? fallbackDurationMinutes;
  const rawHourlyRate = primaryService?.hourly_rate as unknown;
  const hourlyRateNumber =
    typeof rawHourlyRate === 'number' ? rawHourlyRate : parseFloat(String(rawHourlyRate ?? '0'));
  const safeHourlyRate = Number.isNaN(hourlyRateNumber) ? 0 : hourlyRateNumber;
  const getLessonAmountForDuration = (durationMinutes: number): number =>
    Number(((safeHourlyRate * durationMinutes) / 60).toFixed(2));

  useEffect(() => {
    setSelectedDuration(fallbackDurationMinutes);
  }, [fallbackDurationMinutes, instructor.user_id]);
  const effectiveAppliedCreditCents = useMemo(
    () => Math.max(0, Math.round(appliedCreditCents ?? 0)),
    [appliedCreditCents]
  );
  const { data: ratingsData } = useInstructorRatingsQuery(instructor.user_id);
  const rating =
    typeof ratingsData?.overall?.rating === 'number' ? ratingsData.overall.rating : null;
  const reviewCount = ratingsData?.overall?.total_reviews ?? 0;
  const showRating = typeof rating === 'number' && reviewCount >= 3;
  const distanceMi = (instructor as { distance_mi?: number | null }).distance_mi;
  const showDistance = typeof distanceMi === 'number' && Number.isFinite(distanceMi);
  const showFoundingBadge = Boolean(instructor.is_founding_instructor);
  const bgcStatusValue =
    (instructor as { bgc_status?: string | null }).bgc_status ??
    (instructor as { background_check_status?: string | null }).background_check_status ??
    null;
  const bgcStatus = typeof bgcStatusValue === 'string' ? bgcStatusValue.toLowerCase() : '';
  const isLive = Boolean((instructor as { is_live?: boolean }).is_live);
  const backgroundCheckVerified =
    isLive ||
    bgcStatus === 'passed' ||
    bgcStatus === 'clear' ||
    bgcStatus === 'verified' ||
    Boolean(
      (instructor as { background_check_verified?: boolean | null }).background_check_verified
    ) ||
    Boolean(
      (instructor as { background_check_completed?: boolean | null }).background_check_completed
    );
  const showBGCBadge = backgroundCheckVerified || bgcStatus === 'pending';
  const resolvedBgcStatus = bgcStatusValue ?? (backgroundCheckVerified ? 'passed' : null);

  // Use React Query hook for recent reviews (prevents duplicate API calls)
  const { data: recentReviewsData } = useRecentReviews({
    instructorId: instructor.user_id,
    limit: 2,
  });
  const recentReviews = recentReviewsData?.reviews ?? [];
  const serviceAreaBoroughs = getServiceAreaBoroughs(instructor);
  const serviceAreaDisplay = getServiceAreaDisplay(instructor) || 'NYC';
  // Favorite status is now handled by useFavoriteStatus hook (React Query)
  // Recent reviews are now handled by useRecentReviews hook (React Query)

  useEffect(() => {
    if (!bookingDraftId) {
      setPricingPreview(null);
      setPricingPreviewError(null);
      return;
    }

    let cancelled = false;
    const run = async () => {
      setIsPricingPreviewLoading(true);
      setPricingPreviewError(null);
      try {
        const preview = await fetchPricingPreview(bookingDraftId, effectiveAppliedCreditCents);
        if (!cancelled) {
          setPricingPreview(preview);
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiProblemError && error.response.status === 422) {
          setPricingPreviewError(error.problem.detail ?? 'Price is below the minimum.');
        } else {
          setPricingPreviewError('Unable to load pricing preview.');
        }
        setPricingPreview(null);
      } finally {
        if (!cancelled) {
          setIsPricingPreviewLoading(false);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [bookingDraftId, effectiveAppliedCreditCents]);

  // Helper function to calculate end time
const findNextAvailableSlot = (
  availabilityByDate: Record<string, AvailabilityDay>,
  requiredMinutes: number
): NextSlotResult | null => {
    const sortedDates = Object.keys(availabilityByDate).sort();
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    for (const dateStr of sortedDates) {
      const day = availabilityByDate[dateStr];
      if (!day || day.is_blackout) continue;
      const availableSlots = (day.available_slots || []).slice().sort((a, b) => a.start_time.localeCompare(b.start_time));
      const parsedDate = parseIsoDateToLocal(dateStr);
      if (!parsedDate || parsedDate < startOfToday) continue;

      for (const slot of availableSlots) {
        const slotDuration = diffMinutes(slot.start_time, slot.end_time);
        if (slotDuration < requiredMinutes) continue;
        const timeParts = parseTimeToParts(slot.start_time);
        if (!timeParts) continue;

        const slotStartDate = new Date(parsedDate);
        slotStartDate.setHours(timeParts.hour, timeParts.minute, 0, 0);
        if (parsedDate.getTime() === startOfToday.getTime() && slotStartDate <= now) {
          continue;
        }

        const result = {
          date: dateStr,
          time: toHHMM(timeParts.hour, timeParts.minute),
          displayText: formatDisplayText(parsedDate, timeParts.hour, timeParts.minute),
        };

        return result;
      }
    }

    return null;
  };

  // Helper function to get service name from catalog
  const getServiceName = (serviceId: string): string => {
    const service = serviceCatalog.find((s) => s.id === serviceId);
    return service?.name || '';
  };

  const nextAvailableSlot = useMemo(() => {
    if (availabilityData?.availabilityByDate) {
      const slot = findNextAvailableSlot(availabilityData.availabilityByDate, resolvedDurationMinutes);

      return slot;
    }
    return null;
  }, [availabilityData, resolvedDurationMinutes]);


  const handleFavoriteClick = async () => {
    // Guest users - redirect to login
    if (!user) {
      const returnUrl = `/search?instructorToFavorite=${instructor.user_id}`;
      router.push(`/login?returnTo=${encodeURIComponent(returnUrl)}`);
      return;
    }

    if (isLoadingFavorite) return;

    // Optimistic update
    setFavoriteStatus(instructor.user_id, !isFavorited);
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
    } catch {
      // Revert on error
      setFavoriteStatus(instructor.user_id, isFavorited);
      toast.error('Failed to update favorite');
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
              {/* Name with verification badge and rating */}
              <div className={`flex flex-wrap items-center ${compact ? 'gap-2' : 'gap-3'}`}>
                <h2
                  className={`${compact ? 'text-xl' : 'text-3xl'} font-extrabold text-[#7E22CE]`}
                  data-testid="instructor-name"
                >
                  {instructor.user.first_name} {instructor.user.last_initial ? `${instructor.user.last_initial}.` : ''}
                </h2>
                {showDistance && (
                  <span className={`${compact ? 'text-sm' : 'text-base'} font-medium text-gray-500`}>
                    · {distanceMi.toFixed(1)} mi
                  </span>
                )}
              </div>
              {showRating && (
                <button
                  type="button"
                  onClick={() => {
                    router.push(`/instructors/${instructor.user_id}/reviews`);
                  }}
                  className={`mt-1 flex items-center gap-1 text-gray-600 hover:text-[#7E22CE] transition-colors ${compact ? 'text-sm' : 'text-base'} font-medium`}
                  aria-label="See all reviews"
                >
                  <Star className={`${compact ? 'h-4 w-4' : 'h-5 w-5'} text-yellow-500 fill-current`} />
                  <span>{rating}</span>
                  <span>·</span>
                  <span>{reviewCount} reviews</span>
                </button>
              )}

              {showFoundingBadge ? (
                <div className={showRating ? 'mt-1' : ''}>
                  <FoundingBadge size={compact ? 'sm' : 'md'} />
                </div>
              ) : null}

              {showBGCBadge ? (
                <div className={showRating || showFoundingBadge ? 'mt-1' : ''}>
                  <BGCBadge isLive={isLive} bgcStatus={resolvedBgcStatus} />
                </div>
              ) : null}

              {/* Services as pills */}
              <div className={`flex gap-2 ${compact ? 'mt-2 mb-1' : 'mt-3 mb-2'}`}>
                {instructor.services.map((service, idx) => {
                  const serviceName = getServiceName(service.service_catalog_id);
                  if (!serviceName) return null;
                  const isHighlighted =
                    (highlightServiceCatalogId || '').trim().toLowerCase() ===
                    (service.service_catalog_id || '').trim().toLowerCase();
                  return (
                    <span
                      key={`${service.service_catalog_id || service.id || idx}-${serviceName}`}
                      className={`${compact ? 'px-3 py-0.5 text-sm' : 'px-6 py-1 text-lg'} rounded-full font-bold ${
                        isHighlighted ? 'bg-[#7E22CE]/15 text-[#7E22CE]' : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {serviceName}
                    </span>
                  );
                })}
              </div>
              {(() => {
                const highlightId = (highlightServiceCatalogId || '').trim().toLowerCase();
                const context = (instructor as {
                  _matchedServiceContext?: { levels?: string[]; age_groups?: string[]; location_types?: string[] };
                })._matchedServiceContext;
                const contextLevels = context?.levels ?? [];
                const contextAgeGroups = context?.age_groups ?? [];

                const highlightService = highlightId
                  ? instructor.services.find(
                      (svc) => (svc.service_catalog_id || '').trim().toLowerCase() === highlightId,
                    )
                  : null;

                const formatService = highlightService ?? instructor.services[0];
                const offersTravel = Boolean(formatService?.offers_travel);
                const hasTeachingLocations =
                  (Array.isArray((instructor as { teaching_locations?: unknown[] }).teaching_locations) &&
                    (instructor as { teaching_locations?: unknown[] }).teaching_locations!.length > 0) ||
                  (Array.isArray((instructor as { preferred_teaching_locations?: unknown[] }).preferred_teaching_locations) &&
                    (instructor as { preferred_teaching_locations?: unknown[] }).preferred_teaching_locations!.length > 0);
                const offersAtLocation =
                  Boolean(formatService?.offers_at_location) && Boolean(hasTeachingLocations);
                const offersOnline = Boolean(formatService?.offers_online);
                const hasFormat = offersTravel || offersAtLocation || offersOnline;

                const derivedLevels = Array.isArray(highlightService?.levels_taught)
                  ? Array.from(
                      new Set(
                        highlightService!.levels_taught!.map((lvl) => String(lvl).trim().toLowerCase()).filter(Boolean),
                      ),
                    )
                  : [];
                const derivedAgeGroups = Array.isArray(highlightService?.age_groups)
                  ? Array.from(
                      new Set(
                        highlightService!.age_groups!.map((group) => String(group).trim().toLowerCase()).filter(Boolean),
                      ),
                    )
                  : [];

                const levels = contextLevels.length ? contextLevels : derivedLevels;
                const ageGroups = contextAgeGroups.length ? contextAgeGroups : derivedAgeGroups;

                const levelLabel = levels
                  .map((lvl) => lvl.charAt(0).toUpperCase() + lvl.slice(1))
                  .join(' · ');
                const showsKidsBadge = ageGroups.map((g) => g.toLowerCase()).includes('kids');

                const highlightRows: ReactNode[] = [];
                if (showsKidsBadge) {
                  highlightRows.push(
                    <div>
                      <span className="inline-flex items-center bg-yellow-100 text-gray-600 font-semibold px-2 py-1 rounded-full">
                        Kids lesson available
                      </span>
                    </div>
                  );
                }
                if (levelLabel) {
                  highlightRows.push(
                    <div className="flex items-center gap-2">
                      <Layers className="h-3.5 w-3.5 text-[#7E22CE]" aria-hidden="true" />
                      <div>
                        <span className="font-semibold text-[#7E22CE]">Levels:</span>{' '}
                        <span>{levelLabel}</span>
                      </div>
                    </div>
                  );
                }
                if (hasFormat) {
                  highlightRows.push(
                    <div className="flex items-center gap-2">
                      <MonitorSmartphone className="h-3.5 w-3.5 text-[#7E22CE]" aria-hidden="true" />
                      <div>
                        <span className="font-semibold text-[#7E22CE]">Format:</span>{' '}
                        <span className="inline-flex items-center gap-1.5">
                          {offersTravel && (
                            <span role="img" aria-label="Travels to you" title="Travels to you" className="cursor-help">
                              🚗
                            </span>
                          )}
                          {offersAtLocation && (
                            <span
                              role="img"
                              aria-label="At their studio"
                              title="At their studio"
                              className="cursor-help inline-flex items-center"
                            >
                              <MapPin className="h-4 w-4 text-[#7E22CE]" aria-hidden="true" />
                            </span>
                          )}
                          {offersOnline && (
                            <span role="img" aria-label="Online" title="Online" className="cursor-help">
                              💻
                            </span>
                          )}
                        </span>
                      </div>
                    </div>
                  );
                }

                const yearsLabel = instructor.years_experience > 0 ? `${instructor.years_experience} years experience` : '';
                const areaLabel = serviceAreaBoroughs.slice(0, 2).join(', ') || serviceAreaDisplay;

                const metaRows: ReactNode[] = [];
                if (yearsLabel) {
                  metaRows.push(
                    <div className="flex items-center gap-2">
                      <Clock3 className="h-3.5 w-3.5 text-[#7E22CE]" aria-hidden="true" />
                      <div>
                        <span className="font-semibold text-[#7E22CE]">Experience:</span>{' '}
                        <span>{yearsLabel}</span>
                      </div>
                    </div>
                  );
                }

                if (areaLabel) {
                  metaRows.push(
                    <div className="flex items-center gap-2">
                      <MapPin className="h-3.5 w-3.5 text-[#7E22CE]" aria-hidden="true" />
                      <div>
                        <span className="font-semibold text-[#7E22CE]">Service areas:</span>{' '}
                        <span>{areaLabel}</span>
                      </div>
                    </div>
                  );
                }

                const combinedRows = [...highlightRows, ...metaRows];
                if (!combinedRows.length) return null;

                const marginClass = highlightRows.length
                  ? (compact ? 'mt-1 text-xs' : 'mt-2 text-sm')
                  : (compact ? 'mt-1 text-xs' : 'mt-3 text-sm');

                return (
                  <div className={`${marginClass} text-gray-600`}>
                    {combinedRows.map((row, index) => (
                      <div key={index}>
                        {index > 0 && (
                          <div className="h-px w-[70%] ml-0 bg-gradient-to-r from-transparent via-[#7E22CE]/40 to-transparent" />
                        )}
                        <div className="py-2">{row}</div>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>

            {/* Price in upper right */}
            <div className="flex items-start gap-3">
              <div className="flex flex-col items-end text-right">
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
              </div>

              {/* Message Button */}
              <MessageInstructorButton
                instructorId={instructor.user_id}
                instructorName={`${instructor.user.first_name}${instructor.user.last_initial ? ` ${instructor.user.last_initial}.` : ''}`}
                variant="ghost"
                size="sm"
                iconOnly
                className="text-[#7E22CE] hover:bg-purple-50"
              />

              {/* Favorite Button */}
              <button
                onClick={handleFavoriteClick}
                disabled={isLoadingFavorite}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
                aria-label={user ? "Toggle favorite" : "Sign in to save"}
                title={!user ? "Sign in to save this instructor" : isFavorited ? "Remove from favorites" : "Add to favorites"}
              >
                <Heart
                  className={`h-5 w-5 ${isFavorited ? 'fill-red-500 text-red-500' : 'fill-none text-gray-500'}`}
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
          {durationOptions.length > 1 && (
            <div className={`flex items-center gap-2 ${compact ? 'mb-2' : 'mb-4'}`}>
              <p className={`${compact ? 'text-xs' : 'text-sm'} font-medium text-gray-700`}>Duration:</p>
              <div className={`flex ${compact ? 'gap-2' : 'gap-4'}`}>
                {durationOptions.map((duration) => {
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
                        checked={selectedDuration === duration}
                        onChange={() => setSelectedDuration(duration)}
                        className={`${compact ? 'w-3 h-3' : 'w-4 h-4'} text-[#7E22CE] accent-purple-700 border-gray-300 focus:ring-[#7E22CE]`}
                      />
                      <span className={`ml-1 ${compact ? 'text-xs' : 'text-sm'} text-gray-700`}>{duration} min (${price})</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {bookingDraftId ? (
            <div className={`${compact ? 'mb-3' : 'mb-4'}`}>
              {isPricingPreviewLoading ? (
                <p className="text-xs text-gray-500">Updating pricing…</p>
              ) : pricingPreview ? (
                <div className="rounded-lg border border-gray-200 bg-white p-3 text-sm space-y-2">
                  <div className="flex justify-between">
                    <span>Lesson</span>
                    <span>{formatCentsToDisplay(pricingPreview.base_price_cents)}</span>
                  </div>
                  {pricingPreview.line_items.map((item) => {
                    const lowerLabel = (item.label || '').toLowerCase();
                    if (lowerLabel.startsWith('service & support')) {
                      return null;
                    }
                    const isCreditLine = item.amount_cents < 0;
                    return (
                      <div
                        key={`${item.label}-${item.amount_cents}`}
                        className={`flex justify-between text-gray-700 ${
                          isCreditLine ? 'text-green-600 dark:text-green-400' : ''
                        }`}
                      >
                        <span>{item.label}</span>
                        <span>{formatCentsToDisplay(item.amount_cents)}</span>
                      </div>
                    );
                  })}
                  <div className="flex justify-between font-semibold text-base border-t border-gray-200 pt-2">
                    <span>Total</span>
                    <span>{formatCentsToDisplay(pricingPreview.student_pay_cents)}</span>
                  </div>
                </div>
              ) : null}
              {!pricingPreview && pricingPreviewError ? (
                <p className="text-xs text-red-600">{pricingPreviewError}</p>
              ) : null}
            </div>
          ) : null}

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
                    endTime: calculateEndTime(nextAvailableSlot.time, resolvedDurationMinutes),
                    duration: resolvedDurationMinutes,
                    location: '', // Leave empty to let user enter their address
                    basePrice: getLessonAmountForDuration(resolvedDurationMinutes),
                    totalAmount: getLessonAmountForDuration(resolvedDurationMinutes),
                    freeCancellationUntil: parseIsoDateToLocal(nextAvailableSlot.date) ?? new Date(),
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
                    {[1, 2, 3, 4, 5].map((star) => (
                      <Star
                        key={star}
                        className={`h-4 w-4 ${
                          typeof r.rating === 'number' && star <= r.rating
                            ? 'fill-yellow-400 text-yellow-400'
                            : 'fill-gray-200 text-gray-200'
                        }`}
                      />
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

export default memo(InstructorCard);
