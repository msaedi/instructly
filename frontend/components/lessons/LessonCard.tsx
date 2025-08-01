import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Booking } from '@/types/booking';
import { LessonStatus } from './LessonStatus';
import { InstructorInfo } from './InstructorInfo';
import { format } from 'date-fns';
import { Calendar, Clock, DollarSign, ChevronRight } from 'lucide-react';
import { formatLessonStatus } from '@/hooks/useMyLessons';

interface LessonCardProps {
  lesson: Booking;
  isCompleted: boolean;
  onViewDetails: () => void;
  onBookAgain?: () => void;
  onChat?: () => void;
  onReviewTip?: () => void;
}

export function LessonCard({
  lesson,
  isCompleted,
  onViewDetails,
  onBookAgain,
  onChat,
  onReviewTip,
}: LessonCardProps) {
  const lessonDate = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const formattedDate = format(lessonDate, 'EEE MMM d');
  const formattedTime = format(lessonDate, 'h:mmaaa');
  const timeZone = format(lessonDate, 'zzz');

  const displayStatus = formatLessonStatus(lesson.status, lesson.cancelled_at);

  return (
    <Card
      className="p-4 sm:p-6 hover:shadow-lg transition-shadow cursor-pointer"
      onClick={onViewDetails}
    >
      <div className="space-y-4">
        {/* Lesson Title and Status */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
          <div>
            <h3 className="text-lg sm:text-xl font-semibold">{lesson.service_name}</h3>
            {lesson.status !== 'CONFIRMED' && (
              <LessonStatus status={lesson.status} cancelledAt={lesson.cancelled_at} />
            )}
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewDetails();
            }}
            className="text-sm text-primary hover:text-primary/80 flex items-center gap-1 self-start sm:self-auto cursor-pointer"
          >
            See lesson details
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        {/* Date, Time, and Price */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Calendar className="h-4 w-4" />
            <span>{formattedDate}</span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Clock className="h-4 w-4" />
            <span>
              {formattedTime} {timeZone}
            </span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <DollarSign className="h-4 w-4" />
            <span>
              {lesson.status === 'CANCELLED' && lesson.cancelled_at ? (
                <>{getCancellationFeeDisplay(lesson)}</>
              ) : (
                `$${lesson.total_price.toFixed(2)}`
              )}
            </span>
          </div>
        </div>

        {/* Action Button for Completed Lessons */}
        {isCompleted && lesson.status === 'COMPLETED' && (
          <div className="pt-2">
            <Button
              onClick={(e) => {
                e.stopPropagation();
                onBookAgain?.();
              }}
              className="w-full sm:w-auto cursor-pointer"
              variant="default"
            >
              Book Again
            </Button>
          </div>
        )}

        {/* Instructor Info */}
        <div className="pt-4 border-t">
          <InstructorInfo
            instructor={lesson.instructor}
            onChat={(e) => {
              e?.stopPropagation?.();
              onChat?.();
            }}
            showReviewButton={isCompleted && lesson.status === 'COMPLETED'}
            onReview={(e) => {
              e?.stopPropagation?.();
              onReviewTip?.();
            }}
          />
        </div>
      </div>
    </Card>
  );
}

function getCancellationFeeDisplay(lesson: Booking): string {
  if (!lesson.cancelled_at || !lesson.booking_date || !lesson.start_time) {
    return `$${lesson.total_price.toFixed(2)}`;
  }

  const cancelledDate = new Date(lesson.cancelled_at);
  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const hoursBeforeLesson = (lessonDateTime.getTime() - cancelledDate.getTime()) / (1000 * 60 * 60);

  if (hoursBeforeLesson > 24) {
    return '$0.00 (No charge)';
  } else if (hoursBeforeLesson > 12) {
    const charged = lesson.total_price;
    const credit = lesson.total_price / 2;
    return `Charged: $${charged.toFixed(2)} | Credit: $${credit.toFixed(2)}`;
  } else {
    return `$${lesson.total_price.toFixed(2)}`;
  }
}
