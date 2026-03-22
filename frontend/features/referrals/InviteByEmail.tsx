'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { sendReferralInvites } from '@/features/shared/referrals/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/i;

interface InviteByEmailProps {
  shareUrl: string;
  fromName?: string;
  label?: string;
  helperText?: string;
  buttonText?: string;
}

export default function InviteByEmail({
  shareUrl,
  fromName,
  label = 'Invite friends by email',
  helperText = 'Send up to 10 emails at a time. Separate addresses with commas or spaces.',
  buttonText = 'Send invites',
}: InviteByEmailProps) {
  const [inputValue, setInputValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!shareUrl) {
      toast.error('Referral link is still loading. Try again in a moment.');
      setStatusMessage('Referral link is still loading.');
      return;
    }

    const rawEmails = inputValue
      .split(/[\s,;]+/)
      .map((email) => email.trim())
      .filter(Boolean);

    const seen = new Set<string>();
    const valid: string[] = [];
    const invalid: string[] = [];

    rawEmails.forEach((email) => {
      const normalized = email.toLowerCase();
      if (seen.has(normalized)) {
        return;
      }
      seen.add(normalized);
      if (EMAIL_REGEX.test(email)) {
        valid.push(email);
      } else {
        invalid.push(email);
      }
    });

    if (!valid.length) {
      toast.error('Enter at least one valid email');
      setStatusMessage('Enter at least one valid email address.');
      return;
    }

    if (valid.length > 10) {
      toast.error('You can send up to 10 invites at a time.');
      setStatusMessage('Reduce your list to 10 email addresses or fewer.');
      return;
    }

    setIsSubmitting(true);
    setStatusMessage(null);

    try {
      const count = await sendReferralInvites({
        emails: valid,
        shareUrl,
        fromName: fromName || 'A friend',
      });

      toast.success(`Invites sent to ${count} ${count === 1 ? 'address' : 'addresses'}`);
      if (invalid.length) {
        toast.info(`Skipped invalid: ${invalid.join(', ')}`);
      }

      setInputValue('');
      setStatusMessage(`Sent invites to ${count} ${count === 1 ? 'friend' : 'friends'}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to send invites';
      toast.error(message);
      setStatusMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2" aria-live="polite">
      <label htmlFor="invite-emails" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </label>
      <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
        <Input
          id="invite-emails"
          type="text"
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          placeholder="name@example.com, other@example.com"
          className="h-10 flex-1"
          disabled={isSubmitting || !shareUrl}
          aria-describedby="invite-emails-hint"
          autoComplete="off"
        />
        <Button
          type="submit"
          disabled={isSubmitting || !shareUrl}
          className="h-10 whitespace-nowrap"
        >
          {isSubmitting ? 'Sending…' : buttonText}
        </Button>
      </div>
      <p id="invite-emails-hint" className="text-xs text-gray-500 dark:text-gray-400">
        {helperText}
      </p>
      <p className="min-h-[1rem] text-xs text-gray-500 dark:text-gray-400" role="status">
        {statusMessage || (shareUrl ? '' : 'Referral link loading…')}
      </p>
    </form>
  );
}
