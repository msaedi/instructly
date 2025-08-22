import { Card } from '@/components/ui/card';
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
  className?: string;
}

export function LessonCard({
  lesson,
  isCompleted,
  onViewDetails,
  onBookAgain,
  onChat,
  onReviewTip,
  className,
}: LessonCardProps) {
  const lessonDate = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const formattedDate = format(lessonDate, 'EEE MMM d');
  const formattedTime = format(lessonDate, 'h:mmaaa');

  const displayStatus = formatLessonStatus(lesson.status, lesson.cancelled_at);

  return (
    <Card
      className={`p-4 sm:p-6 bg-white rounded-xl border border-gray-200 hover:shadow-lg transition-shadow cursor-pointer ${className || ''}`}
      onClick={onViewDetails}
    >
      <div className="space-y-4">
        {/* Lesson Title and Status */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-2xl sm:text-3xl font-bold text-purple-700">
                {lesson.service_name}
              </h3>
              {isCompleted && lesson.status === 'COMPLETED' && (
                <LessonStatus status={lesson.status} cancelledAt={lesson.cancelled_at} />
              )}
            </div>
            {lesson.status !== 'CONFIRMED' && lesson.status !== 'COMPLETED' && (
              <LessonStatus status={lesson.status} cancelledAt={lesson.cancelled_at} />
            )}
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onViewDetails();
            }}
            className="text-sm text-purple-700 hover:text-purple-800 flex items-center gap-1 self-start sm:self-auto cursor-pointer font-medium"
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
                `${lesson.total_price.toFixed(2)}`
              )}
            </span>
          </div>
        </div>

        {/* Instructor Info */}
        <div className="pt-4 border-t border-gray-300">
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
            showBookAgainButton={isCompleted && lesson.status === 'COMPLETED'}
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
