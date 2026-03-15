'use client';

import Modal from '@/components/Modal';
import { Button } from '@/components/ui/button';
import type { CalendarSettingsAcknowledgementVariant } from './calendarSettings';

interface CalendarSettingsAcknowledgementModalProps {
  isOpen: boolean;
  variant: CalendarSettingsAcknowledgementVariant;
  isSubmitting?: boolean;
  mode?: 'required' | 'info';
  onAcknowledge?: () => void;
  onClose?: () => void;
}

const noop = () => {};

function renderBody(variant: CalendarSettingsAcknowledgementVariant) {
  if (variant === 'mixed_formats') {
    return (
      <>
        <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
          We automatically add buffer time between your lessons so you&apos;re never rushed:
        </p>
        <ul className="list-disc space-y-2 pl-5 text-sm leading-6 text-gray-700 dark:text-gray-300">
          <li>15 minutes between lessons when you&apos;re staying put (online or at your studio)</li>
          <li>60 minutes when you need to travel to a student&apos;s location</li>
        </ul>
        <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
          Students can book up to 1 hour before for online and studio lessons, and up to 3 hours
          before for travel lessons. Early morning slots are protected from overnight bookings by
          default.
        </p>
        <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
          You can adjust buffer times and overnight protection anytime on your availability page.
        </p>
      </>
    );
  }

  if (variant === 'travel_only') {
    return (
      <>
        <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
          We automatically add 60 minutes of buffer time between your lessons to account for travel.
        </p>
        <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
          Students can book up to 3 hours before your lessons. Early morning slots are protected
          from overnight bookings by default.
        </p>
        <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
          You can adjust buffer time and overnight protection anytime on your availability page.
        </p>
      </>
    );
  }

  return (
    <>
      <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
        We automatically add 15 minutes of buffer time between your lessons so you&apos;re never
        rushed.
      </p>
      <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
        Students can book up to 1 hour before your lessons. Early morning slots are protected from
        overnight bookings by default.
      </p>
      <p className="text-sm leading-6 text-gray-700 dark:text-gray-300">
        You can adjust buffer time and overnight protection anytime on your availability page.
      </p>
    </>
  );
}

export default function CalendarSettingsAcknowledgementModal({
  isOpen,
  variant,
  isSubmitting = false,
  mode = 'required',
  onAcknowledge,
  onClose,
}: CalendarSettingsAcknowledgementModalProps) {
  const isRequired = mode === 'required';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose ?? noop}
      title="Your calendar protections are on"
      description="Review how lesson buffers and overnight booking protection work."
      size="sm"
      autoHeight={true}
      closeOnBackdrop={!isRequired}
      closeOnEscape={!isRequired}
      showCloseButton={!isRequired}
      footer={
        <div className="flex justify-end">
          <Button onClick={isRequired ? onAcknowledge : onClose} disabled={isRequired && isSubmitting}>
            {isRequired ? (isSubmitting ? 'Saving…' : 'OK') : 'Close'}
          </Button>
        </div>
      }
    >
      <div className="space-y-4" data-testid="calendar-settings-acknowledgement-modal">
        {renderBody(variant)}
      </div>
    </Modal>
  );
}
