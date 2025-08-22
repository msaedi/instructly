import { Button } from '@/components/ui/button';
import { Star, MessageCircle } from 'lucide-react';

interface InstructorInfoProps {
  instructor?: any; // Can be User or instructor with last_initial
  rating?: number;
  reviewCount?: number;
  lessonsCompleted?: number;
  onChat?: (e?: React.MouseEvent) => void;
  showReviewButton?: boolean;
  onReview?: (e?: React.MouseEvent) => void;
  showBookAgainButton?: boolean;
  onBookAgain?: (e?: React.MouseEvent) => void;
}

// Helper to get instructor display name with privacy (FirstName L.)
function getInstructorPrivacyName(instructor: any): string {
  const firstName = instructor.first_name || '';
  const lastInitial = instructor.last_initial || '';
  return lastInitial ? `${firstName} ${lastInitial}.` : firstName;
}

export function InstructorInfo({
  instructor,
  rating = 4.9,
  reviewCount = 0,
  lessonsCompleted = 0,
  onChat,
  showReviewButton,
  onReview,
  showBookAgainButton,
  onBookAgain,
}: InstructorInfoProps) {
  if (!instructor) {
    return null;
  }

  const displayName = getInstructorPrivacyName(instructor);

  return (
    <div className="flex flex-col sm:flex-row items-start gap-4">
      <div className="flex items-start gap-3 flex-1">
        {/* Avatar */}
        <div className="h-12 w-12 sm:h-14 sm:w-14 bg-gray-200 rounded-full flex items-center justify-center text-gray-500">
          <span className="text-2xl">👤</span>
        </div>

        {/* Instructor Details */}
        <div className="flex-1 min-w-0">
          <p className="font-medium text-foreground">{displayName}</p>
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 text-sm text-muted-foreground">
            <div className="flex items-center gap-1">
              <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
              <span>{rating.toFixed(1)}</span>
              <span>({reviewCount} reviews)</span>
            </div>
            {lessonsCompleted > 0 && (
              <div className="flex items-center gap-1">
                <span>✓</span>
                <span>{lessonsCompleted} lessons completed</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2 w-full sm:w-auto">
        {onChat && !showBookAgainButton && (
          <Button
            onClick={onChat}
            className="flex-1 sm:flex-initial bg-purple-700 hover:bg-purple-800 text-white border-transparent rounded-lg py-2.5 px-6 text-base font-medium"
          >
            <MessageCircle className="h-5 w-5 mr-2" />
            Chat
          </Button>
        )}
        {onChat && showBookAgainButton && (
          <Button
            onClick={onChat}
            className="flex-1 sm:flex-initial bg-white text-gray-400 border-2 border-gray-300 hover:bg-gray-50 rounded-lg py-2 px-4 text-sm font-medium"
          >
            <MessageCircle className="h-4 w-4 mr-1" />
            Chat history
          </Button>
        )}
        {showReviewButton && onReview && (
          <Button
            onClick={onReview}
            className="flex-1 sm:flex-initial bg-white text-purple-700 border-2 border-purple-700 hover:bg-purple-50 rounded-lg py-2 px-4 text-sm font-medium"
          >
            Review & tip
          </Button>
        )}
        {showBookAgainButton && onBookAgain && (
          <Button
            onClick={onBookAgain}
            className="flex-1 sm:flex-initial bg-purple-700 hover:bg-purple-800 text-white border-transparent rounded-lg py-2.5 px-6 text-base font-medium"
          >
            Book Again
          </Button>
        )}
      </div>
    </div>
  );
}
