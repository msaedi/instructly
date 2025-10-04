'use client';

import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import Modal from '@/components/Modal';
import { Button } from '@/components/ui/button';
import { FTC_RIGHTS_URL } from '@/config/constants';

interface BackgroundCheckDisclosureModalProps {
  isOpen: boolean;
  onAccept: () => void;
  onDecline: () => void;
  submitting?: boolean;
}

const DISCLOSURE_SECTIONS = [
  {
    title: 'Information we may obtain',
    body: (
      <>
        <p className="mb-4 text-sm text-gray-700">
          InstaInstru may request a consumer report prepared by Checkr, Inc. that contains information
          about you, including: criminal history records, sex offender registry records, and
          information used to verify your identity such as name, date of birth, Social Security number
          trace, and address history.
        </p>
        <p className="text-sm text-gray-700">
          These reports may be used now or in connection with your ongoing participation on the
          platform. Additional background reports may be obtained throughout your involvement with
          InstaInstru to the extent permitted by law.
        </p>
      </>
    ),
  },
  {
    title: 'Consumer reporting agency contact details',
    body: (
      <div className="text-sm text-gray-700 space-y-1">
        <p>Checkr, Inc.</p>
        <p>One Montgomery Street Suite 2000</p>
        <p>San Francisco, CA 94104</p>
        <p>
          Phone: <a className="text-primary underline" href="tel:844-824-3257">(844) 824-3257</a>
        </p>
        <p>
          Email:{' '}
          <a className="text-primary underline" href="mailto:support@checkr.com">
            support@checkr.com
          </a>
        </p>
        <p>
          Website:{' '}
          <a className="text-primary underline" href="https://checkr.com" target="_blank" rel="noreferrer">
            https://checkr.com
          </a>
        </p>
      </div>
    ),
  },
  {
    title: 'Your rights under the Fair Credit Reporting Act',
    body: (
      <div className="text-sm text-gray-700 space-y-2">
        <p>
          You have the right to receive a copy of any consumer report obtained, dispute incomplete or
          inaccurate information, and request reinvestigation from the consumer reporting agency.
        </p>
        <p>
          Review the official{' '}
          <a className="text-primary underline" href={FTC_RIGHTS_URL} target="_blank" rel="noreferrer">
            Summary of Your Rights Under the Fair Credit Reporting Act
          </a>{' '}
          provided by the Federal Trade Commission.
        </p>
      </div>
    ),
  },
];

const STATE_NOTICE_PLACEHOLDER = (
  <div className="text-sm text-gray-700 space-y-2">
    <p>
      Certain states require additional disclosures or notices. InstaInstru will provide state-
      specific notices that apply to you based on your place of residence and work. Please review any
      supplemental documents provided during onboarding for full details.
    </p>
  </div>
);

export function BackgroundCheckDisclosureModal({
  isOpen,
  onAccept,
  onDecline,
  submitting = false,
}: BackgroundCheckDisclosureModalProps) {
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const [hasScrolledToEnd, setHasScrolledToEnd] = React.useState(false);
  const [statesExpanded, setStatesExpanded] = React.useState(false);

  React.useEffect(() => {
    if (!isOpen) {
      setHasScrolledToEnd(false);
      setStatesExpanded(false);
      if (scrollRef.current) {
        scrollRef.current.scrollTop = 0;
      }
    }
  }, [isOpen]);

  const handleScroll: React.UIEventHandler<HTMLDivElement> = (event) => {
    const { scrollTop, clientHeight, scrollHeight } = event.currentTarget;
    const threshold = 8;
    if (scrollTop + clientHeight >= scrollHeight - threshold) {
      setHasScrolledToEnd(true);
    }
  };

  const handleAccept = () => {
    if (!hasScrolledToEnd || submitting) {
      return;
    }
    onAccept();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onDecline}
      title="Background Check Disclosure and Authorization"
      description="Please review and authorize the background screening disclosure."
      size="lg"
      closeOnBackdrop={!submitting}
      closeOnEscape={!submitting}
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-end sm:items-center">
          <Button variant="outline" onClick={onDecline} disabled={submitting}>
            Decline
          </Button>
          <Button onClick={handleAccept} disabled={!hasScrolledToEnd || submitting}>
            {submitting ? 'Recording…' : 'I acknowledge and authorize'}
          </Button>
          {!hasScrolledToEnd && !submitting && (
            <p className="text-xs text-muted-foreground sm:basis-full sm:text-right">
              Scroll to the end to enable authorization.
            </p>
          )}
        </div>
      }
    >
      <div className="space-y-6" aria-live="polite">
        <div className="sm:hidden">
          <p className="text-sm text-gray-700 mb-2">
            You must review this disclosure before we can start your background check.
          </p>
          <button
            type="button"
            onClick={() => {
              if (scrollRef.current) {
                scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
              }
            }}
            className="text-sm text-primary underline"
          >
            Skip to authorization
          </button>
        </div>
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="max-h-[55vh] overflow-y-auto pr-2 space-y-6"
          role="document"
          tabIndex={0}
          aria-label="Background check disclosure content"
        >
          <section className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <h3 className="text-base font-semibold text-gray-900">Overview</h3>
            <p className="mt-2 text-sm text-gray-700">
              By selecting “I acknowledge and authorize,” you consent to InstaInstru obtaining consumer
              reports about you from a consumer reporting agency for onboarding and participation on
              the platform. These reports may include criminal records, sex offender registry records,
              and identity verification information. Please review the full disclosure below, then
              scroll to the end to authorize.
            </p>
          </section>

          {DISCLOSURE_SECTIONS.map((section) => (
            <section key={section.title}>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">{section.title}</h3>
              {section.body}
            </section>
          ))}

          <section>
            <button
              type="button"
              className="flex w-full items-center justify-between rounded-md border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-900"
              onClick={() => setStatesExpanded((prev) => !prev)}
              aria-expanded={statesExpanded}
            >
              <span>State-specific notices</span>
              {statesExpanded ? (
                <ChevronUp className="h-4 w-4" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
            {statesExpanded && (
              <div className="mt-3 rounded-md border border-gray-100 bg-gray-50 p-4">
                {STATE_NOTICE_PLACEHOLDER}
              </div>
            )}
          </section>

          <section className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <h3 className="text-base font-semibold text-gray-900">Authorization</h3>
            <p className="mt-2 text-sm text-gray-700">
              By selecting “I acknowledge and authorize,” you confirm that you have read the disclosure
              above and authorize InstaInstru to obtain and use consumer reports about you now and
              while you remain active on the platform. You understand that you may revoke this
              authorization by contacting InstaInstru support.
            </p>
          </section>
        </div>
      </div>
    </Modal>
  );
}

export default BackgroundCheckDisclosureModal;
