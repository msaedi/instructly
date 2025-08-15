import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Star, MessageCircle } from 'lucide-react';
import { User } from '@/types/booking';

interface InstructorInfoProps {
  instructor?: any; // Can be User or instructor with last_initial
  rating?: number;
  reviewCount?: number;
  lessonsCompleted?: number;
  onChat?: (e?: React.MouseEvent) => void;
  showReviewButton?: boolean;
  onReview?: (e?: React.MouseEvent) => void;
}

// Helper to get instructor display name with privacy (FirstName L.)
function getInstructorPrivacyName(instructor: any): string {
  const firstName = instructor.first_name || '';
  const lastInitial = instructor.last_initial || '';
  return lastInitial ? `${firstName} ${lastInitial}.` : firstName;
}

// Helper to get initials from instructor
function getInstructorInitials(instructor: any): string {
  const firstInitial = instructor.first_name ? instructor.first_name.charAt(0).toUpperCase() : '';
  const lastInitialChar = instructor.last_initial || '';
  return (firstInitial + lastInitialChar) || '??';
}

export function InstructorInfo({
  instructor,
  rating = 4.9,
  reviewCount = 0,
  lessonsCompleted = 0,
  onChat,
  showReviewButton,
  onReview,
}: InstructorInfoProps) {
  if (!instructor) {
    return null;
  }

  const initials = getInstructorInitials(instructor);
  const displayName = getInstructorPrivacyName(instructor);

  return (
    <div className="flex flex-col sm:flex-row items-start gap-4">
      <div className="flex items-start gap-3 flex-1">
        {/* Avatar */}
        <Avatar className="h-10 w-10 sm:h-12 sm:w-12">
          <AvatarFallback>{initials}</AvatarFallback>
        </Avatar>

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
        {showReviewButton && onReview && (
          <Button
            onClick={onReview}
            size="sm"
            className="flex-1 sm:flex-initial bg-[#6741D9] hover:bg-[#5B4BC3] text-white border-transparent"
          >
            Review & tip
          </Button>
        )}
        {onChat && (
          <Button
            onClick={onChat}
            size="sm"
            className="flex-1 sm:flex-initial bg-[#6741D9] hover:bg-[#5B4BC3] text-white border-transparent"
          >
            <MessageCircle className="h-4 w-4 mr-1" />
            Chat
          </Button>
        )}
      </div>
    </div>
  );
}
