import { cn } from '@/lib/utils';
import type { InstructorProfile } from '@/types/instructor';

interface BookingButtonProps {
  instructor: InstructorProfile;
  className?: string;
  onBook?: () => void;
}

export function BookingButton({ instructor, className, onBook }: BookingButtonProps) {
  const lowestPrice = instructor.services && instructor.services.length > 0
    ? Math.min(...instructor.services.map(s => s.hourly_rate || 0))
    : 0;

  if (!instructor.services || instructor.services.length === 0) {
    return null;
  }

  return (
    <div className={cn(
      "fixed bottom-0 left-0 right-0 z-50 p-4 bg-background border-t",
      className
    )}>
      <button
        className="w-full py-3 px-6 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors"
        onClick={onBook}
      >
        Book Now - From ${lowestPrice}/hr
      </button>
    </div>
  );
}
