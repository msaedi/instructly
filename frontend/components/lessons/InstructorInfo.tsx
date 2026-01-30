import { Button } from '@/components/ui/button';
import { Star, MessageCircle } from 'lucide-react';
import { UserAvatar } from '@/components/user/UserAvatar';

type InstructorSummary = {
  id: string | number;
  first_name?: string;
  last_name?: string;
  last_initial?: string;
  email?: string;
  has_profile_picture?: boolean;
  profile_picture_version?: number;
};

interface InstructorInfoProps {
  instructor?: InstructorSummary; // Can be User or summary with last_initial
  rating?: number;
  reviewCount?: number;
  lessonsCompleted?: number;
  onChat?: (e?: React.MouseEvent) => void;
  showReviewButton?: boolean;
  onReview?: (e?: React.MouseEvent) => void;
  reviewed?: boolean;
  showBookAgainButton?: boolean;
  onBookAgain?: (e?: React.MouseEvent) => void;
  /** Optional callback for viewing reviews. If provided, called instead of navigating. */
  onViewReviews?: (instructorId: string | number) => void;
}

// Helper to get instructor display name with privacy (FirstName L.)
function getInstructorPrivacyName(instructor: InstructorSummary): string {
  const firstName = instructor.first_name || '';
  const lastInitial = instructor.last_initial || '';
  return lastInitial ? `${firstName} ${lastInitial}.` : firstName;
}

export function InstructorInfo({
  instructor,
  rating,
  reviewCount,
  lessonsCompleted = 0,
  onChat,
  showReviewButton,
  onReview,
  reviewed,
  showBookAgainButton,
  onBookAgain,
  onViewReviews,
}: InstructorInfoProps) {
  if (!instructor) {
    return null;
  }

  const displayName = getInstructorPrivacyName(instructor);

  return (
    <div className="flex flex-col sm:flex-row items-start gap-4">
      <div className="flex items-start gap-3 flex-1">
        {/* Avatar */}
        <UserAvatar
          user={{
            id: String(instructor.id),
            ...(instructor.first_name && { first_name: instructor.first_name }),
            ...(instructor.last_name && { last_name: instructor.last_name }),
            ...(instructor.email && { email: instructor.email }),
            ...(instructor.has_profile_picture !== undefined && { has_profile_picture: instructor.has_profile_picture }),
            ...(instructor.profile_picture_version && { profile_picture_version: instructor.profile_picture_version }),
          }}
          size={56}
          className="h-12 w-12 sm:h-14 sm:w-14"
        />

        {/* Instructor Details */}
        <div className="flex-1 min-w-0">
          <p className="font-medium text-foreground">{displayName}</p>
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 text-sm text-muted-foreground">
            {typeof rating === 'number' && typeof reviewCount === 'number' && (
              <div className="flex items-center gap-1">
                <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                <span>{rating.toFixed(1)}</span>
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    if (instructor?.id) {
                      if (onViewReviews) {
                        onViewReviews(instructor.id);
                      } else {
                        window.location.href = `/instructors/${instructor.id}/reviews`;
                      }
                    }
                  }}
                  className="underline-offset-2 hover:underline cursor-pointer"
                  aria-label="See all reviews"
                >
                  ({reviewCount} reviews)
                </button>
              </div>
            )}
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
            className="flex-1 sm:flex-initial bg-[#7E22CE] hover:bg-[#7E22CE] text-white border-transparent rounded-lg py-2.5 px-6 text-base font-medium"
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
        {reviewed ? (
          <span className="flex-1 sm:flex-initial bg-gray-100 text-gray-600 border-2 border-gray-300 rounded-lg py-2 px-4 text-sm font-medium cursor-default">
            Reviewed
          </span>
        ) : (
          showReviewButton && onReview && (
            <Button
              onClick={onReview}
              className="flex-1 sm:flex-initial bg-white text-[#7E22CE] border-2 border-[#7E22CE] hover:bg-purple-50 rounded-lg py-2 px-4 text-sm font-medium"
            >
              Review & tip
            </Button>
          )
        )}
        {showBookAgainButton && onBookAgain && (
          <Button
            onClick={onBookAgain}
            className="flex-1 sm:flex-initial bg-[#7E22CE] hover:bg-[#7E22CE] text-white border-transparent rounded-lg py-2.5 px-6 text-base font-medium"
          >
            Book Again
          </Button>
        )}
      </div>
    </div>
  );
}
