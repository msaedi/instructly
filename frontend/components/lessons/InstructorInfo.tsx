import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Star, MessageCircle } from 'lucide-react';
import { User } from '@/types/booking';

interface InstructorInfoProps {
  instructor?: User;
  rating?: number;
  reviewCount?: number;
  lessonsCompleted?: number;
  onChat?: (e?: React.MouseEvent) => void;
  showReviewButton?: boolean;
  onReview?: (e?: React.MouseEvent) => void;
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

  const initials = instructor.full_name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase();

  return (
    <div className="flex flex-col sm:flex-row items-start gap-4">
      <div className="flex items-start gap-3 flex-1">
        {/* Avatar */}
        <Avatar className="h-10 w-10 sm:h-12 sm:w-12">
          <AvatarImage src={`/api/placeholder/48/48`} alt={instructor.full_name} />
          <AvatarFallback>{initials}</AvatarFallback>
        </Avatar>

        {/* Instructor Details */}
        <div className="flex-1 min-w-0">
          <p className="font-medium text-foreground">{instructor.full_name}</p>
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
          <Button onClick={onReview} variant="outline" size="sm" className="flex-1 sm:flex-initial">
            Review & tip
          </Button>
        )}
        {onChat && (
          <Button onClick={onChat} variant="outline" size="sm" className="flex-1 sm:flex-initial">
            <MessageCircle className="h-4 w-4 mr-1" />
            Chat
          </Button>
        )}
      </div>
    </div>
  );
}
