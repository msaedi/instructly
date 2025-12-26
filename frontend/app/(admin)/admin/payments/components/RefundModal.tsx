import * as Dialog from '@radix-ui/react-dialog';
import { useMemo, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { toast } from 'sonner';

import {
  AdminRefundReason,
  type AdminRefundRequest,
} from '@/src/api/generated/instructly.schemas';
import { useAdminRefundBookingApiV1AdminBookingsBookingIdRefundPost } from '@/src/api/generated/admin-refunds/admin-refunds';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { formatBookingDate, formatBookingTimeRange } from '@/lib/timezone/formatBookingTime';

import type { AdminBooking } from '../hooks/useAdminBookings';
import { formatCurrency } from '../utils';

interface RefundModalProps {
  booking: AdminBooking | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRefunded?: (bookingId: string) => void;
}

const refundOptions = [
  { value: AdminRefundReason.instructor_no_show, label: 'Instructor no-show' },
  { value: AdminRefundReason.dispute, label: 'Dispute' },
  { value: AdminRefundReason.platform_error, label: 'Platform error' },
  { value: AdminRefundReason.other, label: 'Other' },
];

const reasonStatusMap: Record<AdminRefundReason, string> = {
  [AdminRefundReason.instructor_no_show]: 'NO_SHOW',
  [AdminRefundReason.dispute]: 'CANCELLED',
  [AdminRefundReason.platform_error]: 'CANCELLED',
  [AdminRefundReason.other]: 'CANCELLED',
};

export default function RefundModal({ booking, open, onOpenChange, onRefunded }: RefundModalProps) {
  const [reason, setReason] = useState<AdminRefundReason | ''>('');
  const [refundType, setRefundType] = useState<'full' | 'partial'>('full');
  const [partialAmount, setPartialAmount] = useState('');
  const [note, setNote] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const mutation = useAdminRefundBookingApiV1AdminBookingsBookingIdRefundPost();

  const fullAmount = booking?.total_price ?? 0;
  const statusPreview = reason ? reasonStatusMap[reason] : 'CANCELLED';

  const amountCents = useMemo(() => {
    if (refundType === 'partial') {
      const parsed = Number(partialAmount);
      if (Number.isFinite(parsed) && parsed > 0) {
        return Math.round(parsed * 100);
      }
      return null;
    }
    return null;
  }, [partialAmount, refundType]);

  const resetForm = () => {
    setReason('');
    setRefundType('full');
    setPartialAmount('');
    setNote('');
    setFormError(null);
  };

  const handleClose = (nextOpen: boolean) => {
    if (!nextOpen) {
      resetForm();
    }
    onOpenChange(nextOpen);
  };

  const handleSubmit = async () => {
    if (!booking) {
      return;
    }

    if (!reason) {
      setFormError('Select a refund reason to continue.');
      return;
    }

    if (refundType === 'partial' && !amountCents) {
      setFormError('Enter a valid partial refund amount.');
      return;
    }

    setFormError(null);

    const payload: AdminRefundRequest = {
      reason,
    };

    if (note.trim()) {
      payload.note = note.trim();
    }

    if (refundType === 'partial' && amountCents) {
      payload.amount_cents = amountCents;
    }

    try {
      await mutation.mutateAsync({ bookingId: booking.id, data: payload });
      toast.success('Refund issued successfully');
      onRefunded?.(booking.id);
      handleClose(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to issue refund';
      toast.error(message);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-[95vw] max-w-xl -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-2xl">
          <div className="flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold text-gray-900">Issue Refund</Dialog.Title>
            <Dialog.Close asChild>
              <button className="rounded-full p-2 text-gray-500 hover:bg-gray-100" aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {booking ? (
            <div className="mt-4 space-y-4 text-sm text-gray-700">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">Booking</span>
                  <span className="text-xs font-medium text-gray-700">{booking.id}</span>
                </div>
                <div className="mt-2 space-y-1">
                  <p className="font-medium text-gray-900">{booking.student.name}</p>
                  <p>{booking.instructor.name}</p>
                  <p>
                    {booking.service_name} - {formatBookingDate(booking)} -{' '}
                    {formatBookingTimeRange(booking)}
                  </p>
                  <p className="font-semibold">Total Paid: {formatCurrency(fullAmount)}</p>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-gray-500">Reason *</Label>
                <Select value={reason} onValueChange={(value) => setReason(value as AdminRefundReason)}>
                  <SelectTrigger className="bg-white border-gray-200">
                    <SelectValue placeholder="Select reason..." />
                  </SelectTrigger>
                  <SelectContent>
                    {refundOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-gray-500">Amount</Label>
                <div className="space-y-2">
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      checked={refundType === 'full'}
                      onChange={() => setRefundType('full')}
                    />
                    Full refund ({formatCurrency(fullAmount)})
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="radio"
                      checked={refundType === 'partial'}
                      onChange={() => setRefundType('partial')}
                    />
                    Partial refund
                  </label>
                  {refundType === 'partial' ? (
                    <Input
                      value={partialAmount}
                      onChange={(event) => setPartialAmount(event.target.value)}
                      placeholder="Enter amount"
                      className="max-w-xs"
                    />
                  ) : null}
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-gray-500">Admin Note</Label>
                <textarea
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="Explain the refund decision"
                  className="min-h-[90px] w-full rounded-lg border border-gray-200 p-3 text-sm"
                />
              </div>

              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />
                  <div>
                    <p className="font-semibold">This action will:</p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
                      <li>Refund {refundType === 'partial' && amountCents ? formatCurrency(amountCents / 100) : formatCurrency(fullAmount)} to student</li>
                      <li>Reverse instructor payout proportionally</li>
                      <li>Update booking status to {statusPreview}</li>
                    </ul>
                  </div>
                </div>
              </div>

              {formError ? <p className="text-xs text-rose-600">{formError}</p> : null}

              <div className="flex justify-end gap-3">
                <Dialog.Close asChild>
                  <button className="rounded-full px-4 py-2 text-sm font-medium ring-1 ring-gray-300 hover:bg-gray-100">
                    Cancel
                  </button>
                </Dialog.Close>
                <button
                  type="button"
                  onClick={() => void handleSubmit()}
                  disabled={mutation.isPending}
                  className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:brightness-110 disabled:opacity-50"
                >
                  {mutation.isPending ? 'Issuing...' : 'Issue Refund'}
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-4 text-sm text-gray-500">Select a booking to issue a refund.</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
