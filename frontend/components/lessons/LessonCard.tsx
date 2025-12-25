import { Card } from '@/components/ui/card';
import { useEffect, useState } from 'react';
import { reviewsApi } from '@/services/api/reviews';
import { Booking } from '@/types/booking';
import { LessonStatus } from './LessonStatus';
import { InstructorInfo } from './InstructorInfo';
import { Calendar, Clock, DollarSign, ChevronRight } from 'lucide-react';
import { formatBookingDate, formatBookingTime } from '@/lib/timezone/formatBookingTime';
// formatLessonStatus utility available at: '@/hooks/useMyLessons'

interface LessonCardProps {
  lesson: Booking;
  isCompleted: boolean;
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
  const [reviewed, setReviewed] = useState<boolean | null>(null);
  const formattedDate = formatBookingDate(lesson);
  const formattedTime = formatBookingTime(lesson);

  // Status formatting helper available: formatLessonStatus(lesson.status, lesson.cancelled_at)

  useEffect(() => {
    // If a prefetched value is provided, always use it and skip fetching
    if (typeof prefetchedReviewed === 'boolean') {
      setReviewed(prefetchedReviewed);
      return;
    }
    if (suppressFetchReviewed) {
      return;
    }
    let mounted = true;
    // Only check for completed lessons where review CTA might show
    if (isCompleted && (lesson.status === 'COMPLETED' || lesson.status === 'CONFIRMED')) {
      (async () => {
        try {
          const r = await reviewsApi.getByBooking(lesson.id);
          if (mounted) setReviewed(!!r);
        } catch {
          if (mounted) setReviewed(false);
        }
      })();
    } else {
      setReviewed(null);
    }
    return () => {
      mounted = false;
    };
  }, [isCompleted, lesson.id, lesson.status, prefetchedReviewed, suppressFetchReviewed]);

  const [rating, setRating] = useState<number | undefined>(undefined);
  const [reviewCount, setReviewCount] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (suppressFetchRating) {
      // Use prefetched if present, else skip
      if (typeof prefetchedRating === 'number' && typeof prefetchedReviewCount === 'number') {
        setRating(prefetchedRating);
        setReviewCount(prefetchedReviewCount);
      }
      return;
    }
    if (typeof prefetchedRating === 'number' && typeof prefetchedReviewCount === 'number') {
      setRating(prefetchedRating);
      setReviewCount(prefetchedReviewCount);
      return;
    }
    let mounted = true;
    (async () => {
      try {
        const data = await reviewsApi.getInstructorRatings(lesson.instructor_id);
        if (!mounted || !data) return;
        const count = data.overall?.total_reviews ?? 0;
        setReviewCount(count);
        // Only show rating when we have enough reviews (threshold aligned with backend display)
        if (count >= 3) {
          setRating(data.overall?.rating ?? undefined);
        } else {
          setRating(undefined);
        }
      } catch {
        if (mounted) {
          setRating(undefined);
          setReviewCount(undefined);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [lesson.instructor_id, prefetchedRating, prefetchedReviewCount, suppressFetchRating]);

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
              {(lesson.status === 'COMPLETED' || (isCompleted && lesson.status === 'CONFIRMED')) && (
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
