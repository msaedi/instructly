import { Card } from '@/components/ui/card';
import { useMemo } from 'react';
import { reviewsApi } from '@/services/api/reviews';
import { Booking } from '@/types/booking';
import { LessonStatus } from './LessonStatus';
import { InstructorInfo } from './InstructorInfo';
import { Calendar, Clock, DollarSign, ChevronRight } from 'lucide-react';
import { formatBookingDate, formatBookingTime } from '@/lib/timezone/formatBookingTime';
import { useQuery } from '@tanstack/react-query';
// formatLessonStatus utility available at: '@/hooks/useMyLessons'

interface LessonCardProps {
  lesson: Booking;
  isCompleted: boolean;
  isInProgress?: boolean;
  onViewDetails: () => void;
  onBookAgain?: () => void;
  onChat?: () => void;
  onReviewTip?: () => void;
  className?: string;
  prefetchedRating?: number;
  prefetchedReviewCount?: number;
  prefetchedReviewed?: boolean;
  suppressFetchRating?: boolean;
  suppressFetchReviewed?: boolean;
}

export function LessonCard({
  lesson,
  isCompleted,
  isInProgress = false,
  onViewDetails,
  onBookAgain,
  onChat,
  onReviewTip,
  className,
  prefetchedRating,
  prefetchedReviewCount,
  prefetchedReviewed,
  suppressFetchRating,
  suppressFetchReviewed,
}: LessonCardProps) {
  const formattedDate = formatBookingDate(lesson);
  const formattedTime = formatBookingTime(lesson);
  const showInProgressBadge = lesson.status === 'CONFIRMED' && isInProgress;
  const showCompletedBadge =
    lesson.status === 'COMPLETED' ||
    (lesson.status === 'CONFIRMED' && isCompleted && !showInProgressBadge);

  // Status formatting helper available: formatLessonStatus(lesson.status, lesson.booking_date, lesson.cancelled_at)

  const shouldFetchReviewed = Boolean(
    !suppressFetchReviewed &&
      typeof prefetchedReviewed !== 'boolean' &&
      isCompleted &&
      (lesson.status === 'COMPLETED' || lesson.status === 'CONFIRMED')
  );
  const {
    data: reviewedData,
    isError: reviewedError,
  } = useQuery({
    queryKey: ['lesson-reviewed', lesson.id],
    queryFn: () => reviewsApi.getByBooking(lesson.id),
    enabled: shouldFetchReviewed,
  });
  const reviewed = useMemo(() => {
    if (typeof prefetchedReviewed === 'boolean') return prefetchedReviewed;
    if (suppressFetchReviewed) return null;
    if (!shouldFetchReviewed) return null;
    if (reviewedError) return false;
    return Boolean(reviewedData);
  }, [prefetchedReviewed, suppressFetchReviewed, shouldFetchReviewed, reviewedData, reviewedError]);

  const shouldFetchRating = Boolean(
    !suppressFetchRating &&
      !(typeof prefetchedRating === 'number' && typeof prefetchedReviewCount === 'number')
  );
  const {
    data: ratingData,
    isError: ratingError,
  } = useQuery({
    queryKey: ['instructor-ratings', lesson.instructor_id],
    queryFn: () => reviewsApi.getInstructorRatings(lesson.instructor_id),
    enabled: shouldFetchRating,
  });
  const { rating, reviewCount } = useMemo(() => {
    if (typeof prefetchedRating === 'number' && typeof prefetchedReviewCount === 'number') {
      const count = prefetchedReviewCount;
      return {
        rating: count >= 3 ? prefetchedRating : undefined,
        reviewCount: count,
      };
    }
    if (suppressFetchRating) {
      return { rating: undefined, reviewCount: undefined };
    }
    if (!shouldFetchRating || ratingError || !ratingData) {
      return { rating: undefined, reviewCount: undefined };
    }
    const count = ratingData.overall?.total_reviews ?? 0;
    return {
      rating: count >= 3 ? ratingData.overall?.rating ?? undefined : undefined,
      reviewCount: count,
    };
  }, [
    prefetchedRating,
    prefetchedReviewCount,
    suppressFetchRating,
    shouldFetchRating,
    ratingData,
    ratingError,
  ]);

  return (
    <Card
      className={`p-4 sm:p-6 bg-white rounded-xl border border-gray-200 hover:shadow-lg transition-shadow cursor-pointer ${className || ''}`}
      data-testid="lesson-card"
      onClick={onViewDetails}
    >
      <div className="space-y-4">
        {/* Lesson Title and Status */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-2xl sm:text-3xl font-bold text-[#7E22CE]">
                {lesson.service_name}
              </h3>
              {/* Show completed badge for completed lessons or past confirmed lessons */}
              {showInProgressBadge && <LessonStatus status="IN_PROGRESS" />}
              {showCompletedBadge && (
                <LessonStatus status="COMPLETED" {...(lesson.cancelled_at && { cancelledAt: lesson.cancelled_at })} />
              )}
              {/* Show cancelled badge inline for cancelled lessons */}
              {lesson.status === 'CANCELLED' && (
                <LessonStatus status="CANCELLED" {...(lesson.cancelled_at && { cancelledAt: lesson.cancelled_at })} />
              )}
              {/* Show no-show badge inline for no-show lessons */}
              {lesson.status === 'NO_SHOW' && (
                <LessonStatus status="NO_SHOW" {...(lesson.cancelled_at && { cancelledAt: lesson.cancelled_at })} />
              )}
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewDetails();
            }}
            className="text-sm text-[#7E22CE] hover:text-[#7E22CE] flex items-center gap-1 self-start sm:self-auto cursor-pointer font-medium"
          >
            See lesson details
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        {/* Date, Time, and Price */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-gray-600">
            <Calendar className="h-4 w-4" />
            <span className="text-lg">{formattedDate}</span>
          </div>
          <div className="flex items-center gap-2 text-gray-600">
            <Clock className="h-4 w-4" />
            <span className="text-lg">{formattedTime}</span>
          </div>
          <div className="flex items-center gap-2 text-gray-600">
            <DollarSign className="h-4 w-4" />
            <span className="text-lg font-medium">
              {lesson.status === 'CANCELLED' && lesson.cancelled_at ? (
                <>{getCancellationFeeDisplay(lesson)}</>
              ) : (
                formatMoney(lesson.total_price)
              )}
            </span>
          </div>
        </div>

        {/* Instructor Info */}
        <div className="pt-4 border-t border-gray-300">
          <InstructorInfo
            {...(lesson.instructor && { instructor: lesson.instructor })}
            {...(rating && { rating })}
            {...(reviewCount && { reviewCount })}
            onChat={(e) => {
              e?.stopPropagation?.();
              onChat?.();
            }}
            showReviewButton={isCompleted && (lesson.status === 'COMPLETED' || lesson.status === 'CONFIRMED')}
            reviewed={Boolean(reviewed)}
            onReview={(e) => {
              e?.stopPropagation?.();
              onReviewTip?.();
            }}
            showBookAgainButton={(isCompleted && (lesson.status === 'COMPLETED' || lesson.status === 'CONFIRMED')) || lesson.status === 'CANCELLED'}
            onBookAgain={(e) => {
              e?.stopPropagation?.();
              onBookAgain?.();
            }}
          />
        </div>
      </div>
    </Card>
  );
}

function getCancellationFeeDisplay(lesson: Booking): string {
  if (!lesson.cancelled_at || !lesson.booking_date || !lesson.start_time) {
    return formatMoney(lesson.total_price);
  }

  const cancelledDate = new Date(lesson.cancelled_at);
  const bookingStartUtc = (lesson as { booking_start_utc?: string | null }).booking_start_utc;
  const lessonDateTime = bookingStartUtc
    ? new Date(bookingStartUtc)
    : new Date(`${lesson.booking_date}T${lesson.start_time}Z`);
  const hoursBeforeLesson = (lessonDateTime.getTime() - cancelledDate.getTime()) / (1000 * 60 * 60);

  if (hoursBeforeLesson > 24) {
    return '$0.00 (No charge)';
  } else if (hoursBeforeLesson > 12) {
    const price = toNumber(lesson.total_price);
    if (price == null) return '—';
    const charged = price;
    const credit = price / 2;
    return `Charged: $${charged.toFixed(2)} | Credit: $${credit.toFixed(2)}`;
  } else {
    return formatMoney(lesson.total_price);
  }
}

function toNumber(val: unknown): number | null {
  return typeof val === 'number' && Number.isFinite(val) ? val : null;
}

function formatMoney(val: unknown, fallback: string = '—'): string {
  const n = toNumber(val);
  return n == null ? fallback : `$${n.toFixed(2)}`;
}
