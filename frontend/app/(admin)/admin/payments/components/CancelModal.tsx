import * as Dialog from '@radix-ui/react-dialog';
import { useState } from 'react';
import { X } from 'lucide-react';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import type { AdminBooking } from '../hooks/useAdminBookings';

interface CancelModalProps {
  booking: AdminBooking | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (booking: AdminBooking, reason: string, note: string, refund: boolean) => void;
}

export default function CancelModal({ booking, open, onOpenChange, onConfirm }: CancelModalProps) {
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [refund, setRefund] = useState(true);

  const handleClose = (next: boolean) => {
    if (!next) {
      setReason('');
      setNote('');
      setRefund(true);
    }
    onOpenChange(next);
  };

  const handleConfirm = () => {
    if (!booking) {
      return;
    }
    onConfirm(booking, reason.trim(), note.trim(), refund);
    handleClose(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={handleClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-[95vw] max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-2xl">
          <div className="flex items-center justify-between">
            <Dialog.Title className="text-lg font-semibold text-gray-900">Cancel Booking</Dialog.Title>
            <Dialog.Close asChild>
              <button className="rounded-full p-2 text-gray-500 hover:bg-gray-100" aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {booking ? (
            <div className="mt-4 space-y-4 text-sm text-gray-700">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <p className="text-xs text-gray-500">Booking</p>
                <p className="font-medium text-gray-900">{booking.id}</p>
                <p>{booking.student.name} - {booking.instructor.name}</p>
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-gray-500">Reason</Label>
                <Input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Why is this booking cancelled?"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-gray-500">Admin Note</Label>
                <textarea
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder="Add context for audit log"
                  className="min-h-[90px] w-full rounded-lg border border-gray-200 p-3 text-sm"
                />
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={refund} onChange={(event) => setRefund(event.target.checked)} />
                Issue refund with cancellation
              </label>

              <div className="flex justify-end gap-3">
                <Dialog.Close asChild>
                  <button className="rounded-full px-4 py-2 text-sm font-medium ring-1 ring-gray-300 hover:bg-gray-100">
                    Close
                  </button>
                </Dialog.Close>
                <button
                  type="button"
                  onClick={handleConfirm}
                  className="rounded-full bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:brightness-110"
                >
                  Cancel Booking
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-4 text-sm text-gray-500">Select a booking to cancel.</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
