import { StatusBadge, StatusBadgeVariant } from '@/components/ui/status-badge';
import { BookingStatus } from '@/types/booking';

interface LessonStatusProps {
  status: BookingStatus;
  cancelledAt?: string;
}

export function LessonStatus({ status, cancelledAt }: LessonStatusProps) {
  const getVariantAndLabel = (): { variant: StatusBadgeVariant; label: string } => {
    switch (status) {
      case 'CONFIRMED':
        return { variant: 'pending', label: 'Upcoming' };
      case 'COMPLETED':
        return { variant: 'success', label: 'Completed' };
      case 'CANCELLED':
        return { variant: 'cancelled', label: 'Cancelled' };
      case 'NO_SHOW':
        return { variant: 'warning', label: 'No Show' };
      default:
        return { variant: 'default', label: status };
    }
  };

  const { variant, label } = getVariantAndLabel();

  return <StatusBadge variant={variant} label={label} />;
}
