'use client';

import Link from 'next/link';
import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ArrowLeft, Settings, ChevronDown, Shield, Power, KeyRound, Gift } from 'lucide-react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import TfaModal from '@/components/security/TfaModal';
import ChangePasswordModal from '@/components/security/ChangePasswordModal';
import DeleteAccountModal from '@/components/security/DeleteAccountModal';
import PauseAccountModal from '@/components/security/PauseAccountModal';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { useUser } from '@/hooks/queries/useUser';
import { useUserAddresses, useInvalidateUserAddresses } from '@/hooks/queries/useUserAddresses';
import { useTfaStatus, useInvalidateTfaStatus } from '@/hooks/queries/useTfaStatus';
import { usePushNotifications } from '@/features/shared/hooks/usePushNotifications';
import { useNotificationPreferences } from '@/features/shared/hooks/useNotificationPreferences';
import { usePhoneVerification } from '@/features/shared/hooks/usePhoneVerification';

const RewardsPanel = dynamic(() => import('@/features/referrals/RewardsPanel'), { ssr: false });

const PREFERENCE_DEFAULTS = {
  lesson_updates: { email: true, push: true, sms: false },
  messages: { email: false, push: true, sms: false },
  reviews: { email: true, push: true, sms: false },
  learning_tips: { email: true, push: true, sms: false },
  system_updates: { email: true, push: false, sms: false },
  promotional: { email: false, push: false, sms: false },
} as const;
const E164_PATTERN = /^\+[1-9]\d{7,14}$/;

type PreferenceCategory = keyof typeof PREFERENCE_DEFAULTS;
type PreferenceChannel = keyof (typeof PREFERENCE_DEFAULTS)['lesson_updates'];

const CATEGORY_LABELS: Record<PreferenceCategory, string> = {
  lesson_updates: 'Lesson Updates',
  messages: 'Messages',
  reviews: 'Reviews',
  learning_tips: 'Tips & Updates',
  system_updates: 'System Updates',
  promotional: 'Promotional',
};

const CHANNEL_LABELS: Record<PreferenceChannel, string> = {
  email: 'Email',
  sms: 'SMS',
  push: 'Push',
};

export function SettingsImpl({ embedded = false }: { embedded?: boolean }) {
  const [openAccount, setOpenAccount] = useState(false);
  const [openRefer, setOpenRefer] = useState(false);
  const [openSecurity, setOpenSecurity] = useState(false);
  const [openStatus, setOpenStatus] = useState(false);
  const [openPassword, setOpenPassword] = useState(false);
  const [openPreferences, setOpenPreferences] = useState(false);
  const [showTfaModal, setShowTfaModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showPauseModal, setShowPauseModal] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [zip, setZip] = useState('');
  const [savingAccount, setSavingAccount] = useState(false);
  const [formInitialized, setFormInitialized] = useState(false);
  const [smsPhone, setSmsPhone] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [resendCooldown, setResendCooldown] = useState(0);

  // React Query hooks for data fetching (replaces useEffect fetches)
  const { data: tfaStatus } = useTfaStatus(embedded && openSecurity);
  const { data: userData, isLoading: userLoading } = useUser();
  const { data: addressData, isLoading: addressLoading } = useUserAddresses(embedded);
  const invalidateTfaStatus = useInvalidateTfaStatus();
  const invalidateAddresses = useInvalidateUserAddresses();
  const {
    isSupported: pushSupported,
    permission: pushPermission,
    isSubscribed: pushEnabled,
    isLoading: pushLoading,
    error: pushError,
    subscribe: enablePush,
    unsubscribe: disablePush,
  } = usePushNotifications();
  const {
    preferences,
    isLoading: preferencesLoading,
    isUpdating: preferencesUpdating,
    updatePreference,
  } = useNotificationPreferences();
  const {
    phoneNumber,
    isVerified: phoneVerified,
    isLoading: phoneLoading,
    updatePhone,
    sendVerification,
    confirmVerification,
  } = usePhoneVerification();

  // Derived state from hooks
  const tfaEnabled = tfaStatus?.enabled ?? null;
  const accountLoading = userLoading || addressLoading;
  const pushDisabled = !pushSupported || pushLoading || pushPermission === 'denied';
  const preferencesDisabled = preferencesLoading || preferencesUpdating;
  const pushPreferenceDisabled =
    preferencesDisabled || !pushSupported || pushPermission === 'denied' || !pushEnabled;
  const pushToggleTitle = !pushSupported
    ? 'Push notifications are not supported in this browser.'
    : pushPermission === 'denied'
      ? 'Enable notifications in your browser settings to turn this on.'
      : undefined;
  const pushPreferenceTitle = !pushSupported
    ? 'Push notifications are not supported in this browser.'
    : pushPermission === 'denied'
      ? 'Enable notifications in your browser settings to manage push preferences.'
      : !pushEnabled
        ? 'Enable push notifications on this device to manage push preferences.'
        : undefined;
  const smsPreferenceDisabled = preferencesDisabled || phoneLoading || !phoneNumber || !phoneVerified;
  const smsPreferenceTitle = !phoneNumber
    ? 'Add a phone number to enable SMS notifications.'
    : !phoneVerified
      ? 'Verify your phone number to enable SMS notifications.'
      : undefined;

  const handlePushToggle = async (enabled: boolean) => {
    if (enabled) {
      await enablePush();
    } else {
      await disablePush();
    }
  };

  useEffect(() => {
    if (phoneLoading) return;
    setSmsPhone(phoneNumber || '');
  }, [phoneNumber, phoneLoading]);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setTimeout(() => {
      setResendCooldown((value) => Math.max(0, value - 1));
    }, 1000);
    return () => clearTimeout(timer);
  }, [resendCooldown]);

  const handleUpdatePhone = async () => {
    const trimmed = smsPhone.trim();
    if (!trimmed) {
      toast.error('Please enter a phone number.');
      return;
    }
    if (!E164_PATTERN.test(trimmed)) {
      toast.error('Phone number must be in E.164 format (+1234567890).');
      return;
    }
    const previousPhone = phoneNumber;
    const wasVerified = phoneVerified;
    try {
      const updated = await updatePhone.mutateAsync(trimmed);
      setMobile(trimmed);
      setSmsCode('');
      const shouldSendVerification =
        !updated.verified && (trimmed !== previousPhone || !wasVerified);
      if (shouldSendVerification) {
        try {
          await sendVerification.mutateAsync();
          setResendCooldown(60);
          toast.success('Phone number saved. Verification code sent.');
        } catch (error) {
          toast.error(
            error instanceof Error
              ? error.message
              : 'Phone saved, but failed to send verification code.'
          );
        }
      } else {
        toast.success('Phone number saved.');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update phone number.');
    }
  };

  const handleSendVerification = async () => {
    if (resendCooldown > 0 || sendVerification.isPending) return;
    try {
      await sendVerification.mutateAsync();
      setResendCooldown(60);
      toast.success('Verification code sent.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to send verification code.');
    }
  };

  const handleConfirmVerification = async () => {
    const trimmed = smsCode.trim();
    if (!trimmed) {
      toast.error('Enter the verification code.');
      return;
    }
    try {
      await confirmVerification.mutateAsync(trimmed);
      setSmsCode('');
      toast.success('Phone number verified.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Verification failed.');
    }
  };

  const renderPushToggle = () => (
    <ToggleSwitch
      checked={pushEnabled}
      onChange={() => void handlePushToggle(!pushEnabled)}
      disabled={pushDisabled}
      ariaLabel="Push notifications on this device"
      {...(pushToggleTitle ? { title: pushToggleTitle } : {})}
    />
  );

  const renderPushStatus = () => (
    <div className="mt-2 space-y-1 text-xs">
      {!pushSupported && <p className="text-gray-500">Push notifications are not supported in this browser.</p>}
      {pushPermission === 'denied' && (
        <p className="text-amber-600">Enable notifications in your browser settings to receive push alerts.</p>
      )}
      {pushLoading && <p className="text-gray-500">Updating push notifications…</p>}
      {pushError && <p className="text-red-600">{pushError}</p>}
    </div>
  );

  const getPreferenceValue = (category: PreferenceCategory, channel: PreferenceChannel) => {
    const fallback = PREFERENCE_DEFAULTS[category][channel];
    return preferences?.[category]?.[channel] ?? fallback;
  };

  const ToggleSwitch = ({
    checked,
    onChange,
    disabled = false,
    title,
    ariaLabel,
  }: {
    checked: boolean;
    onChange: () => void;
    disabled?: boolean;
    title?: string;
    ariaLabel?: string;
  }) => (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-disabled={disabled}
      aria-label={ariaLabel}
      onClick={onChange}
      disabled={disabled}
      title={title}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        checked ? 'bg-purple-600' : 'bg-gray-200'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );

  const renderPreferenceToggle = (
    category: PreferenceCategory,
    channel: PreferenceChannel,
    options?: { disabled?: boolean; title?: string }
  ) => {
    const isDisabled = options?.disabled ?? preferencesDisabled;
    const title = options?.title;
    const ariaLabel = `${CATEGORY_LABELS[category]} ${CHANNEL_LABELS[channel]} notifications`;
    return (
      <ToggleSwitch
        checked={getPreferenceValue(category, channel)}
        onChange={() => updatePreference(category, channel, !getPreferenceValue(category, channel))}
        disabled={isDisabled}
        ariaLabel={ariaLabel}
        {...(title ? { title } : {})}
      />
    );
  };

  const renderNotificationPreferences = () => {
    const pushPreferenceOptions = pushPreferenceTitle
      ? { disabled: pushPreferenceDisabled, title: pushPreferenceTitle }
      : { disabled: pushPreferenceDisabled };
    const smsPreferenceOptions = smsPreferenceTitle
      ? { disabled: smsPreferenceDisabled, title: smsPreferenceTitle }
      : { disabled: smsPreferenceDisabled };

    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-gray-200 p-3 space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-900">Phone number (for SMS)</label>
            <p className="text-xs text-gray-500">Add and verify a phone number to receive SMS alerts.</p>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <input
              type="tel"
              value={smsPhone}
              onChange={(event) => setSmsPhone(event.target.value)}
              placeholder="+1 (555) 123-4567"
              className="w-full max-w-sm px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/40"
            />
            <button
              type="button"
              onClick={handleUpdatePhone}
              disabled={updatePhone.isPending}
              className="min-w-[100px] inline-flex items-center justify-center gap-2 rounded-md bg-[#7E22CE] text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {updatePhone.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
          {phoneVerified && (
            <p className="text-xs font-medium text-green-600">Phone verified</p>
          )}
          {!phoneVerified && phoneNumber && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <input
                type="text"
                value={smsCode}
                onChange={(event) => setSmsCode(event.target.value.replace(/\D/g, ''))}
                placeholder="Enter 6-digit code"
                className="w-full max-w-sm px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/40"
                maxLength={6}
              />
              <button
                type="button"
                onClick={handleConfirmVerification}
                disabled={confirmVerification.isPending}
                className="min-w-[100px] inline-flex items-center justify-center gap-2 rounded-md bg-[#7E22CE] text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {confirmVerification.isPending ? 'Verifying…' : 'Verify'}
              </button>
              <button
                type="button"
                onClick={handleSendVerification}
                disabled={sendVerification.isPending || resendCooldown > 0}
                className={`min-w-[100px] inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition-colors ${
                  resendCooldown > 0 || sendVerification.isPending
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-[#7E22CE] text-white hover:bg-[#6b1fb8]'
                }`}
              >
                {resendCooldown > 0
                  ? `Resend (${resendCooldown}s)`
                  : sendVerification.isPending
                    ? 'Sending…'
                    : 'Resend'}
              </button>
            </div>
          )}
        </div>
        <div className="rounded-lg border border-gray-200 p-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-900">Push notifications on this device</p>
              <p className="text-xs text-gray-500">
                Enable push notifications in this browser to receive alerts.
              </p>
            </div>
            {renderPushToggle()}
          </div>
          {renderPushStatus()}
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4 pb-3 border-b border-gray-200">
            <div className="text-sm font-medium text-gray-700">Notification Type</div>
            <div className="text-sm font-medium text-gray-700 text-center">Email</div>
            <div className="text-sm font-medium text-gray-700 text-center">SMS</div>
            <div className="text-sm font-medium text-gray-700 text-center">Push</div>
          </div>

          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Lesson Updates</div>
              <div className="text-xs text-gray-500">Booking confirmations, reminders, cancellations</div>
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('lesson_updates', 'email')}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('lesson_updates', 'sms', smsPreferenceOptions)}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('lesson_updates', 'push', pushPreferenceOptions)}
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Messages</div>
              <div className="text-xs text-gray-500">Direct messages from students</div>
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('messages', 'email')}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('messages', 'sms', smsPreferenceOptions)}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('messages', 'push', {
                disabled: true,
                title: 'Push notifications for messages are required.',
              })}
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Reviews</div>
              <div className="text-xs text-gray-500">New reviews, review responses</div>
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('reviews', 'email')}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('reviews', 'sms', smsPreferenceOptions)}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('reviews', 'push', pushPreferenceOptions)}
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Tips &amp; Updates</div>
              <div className="text-xs text-gray-500">Platform tips and learning resources</div>
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('learning_tips', 'email')}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('learning_tips', 'sms', smsPreferenceOptions)}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('learning_tips', 'push', pushPreferenceOptions)}
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">System Updates</div>
              <div className="text-xs text-gray-500">
                Important platform notices and policy changes
              </div>
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('system_updates', 'email')}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('system_updates', 'sms', smsPreferenceOptions)}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('system_updates', 'push', pushPreferenceOptions)}
            </div>
          </div>

          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Promotional</div>
              <div className="text-xs text-gray-500">Discounts, special offers, new features</div>
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('promotional', 'email')}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('promotional', 'sms', smsPreferenceOptions)}
            </div>
            <div className="flex justify-center">
              {renderPreferenceToggle('promotional', 'push', pushPreferenceOptions)}
            </div>
          </div>
        </div>
    </div>
    );
  };

  // Sync hook data to local editable state (once on initial load)
  useEffect(() => {
    if (!embedded || formInitialized) return;
    if (userData) {
      const fn = (userData.first_name || '').toString().trim();
      const ln = (userData.last_name || '').toString().trim();
      setFullName([fn, ln].filter(Boolean).join(' ').trim());
      setEmail((userData.email || '').toString());
      setMobile((userData.phone || '').toString());
    }
    if (addressData?.items) {
      const items = addressData.items;
      const def = items.find((a) => a.is_default) || (items.length > 0 ? items[0] : null);
      if (def) setZip((def.postal_code || '').toString());
    }
    if (userData && addressData) {
      setFormInitialized(true);
    }
  }, [embedded, formInitialized, userData, addressData]);

  const handleSaveAccount = async () => {
    try {
      setSavingAccount(true);
      const trimmed = (fullName || '').trim();
      const parts = trimmed.split(/\s+/);
      const lastName = parts.length > 1 ? parts.pop() || '' : '';
      const firstName = parts.join(' ');

      try {
        await fetchWithAuth(API_ENDPOINTS.ME, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            first_name: firstName,
            last_name: lastName,
            phone: (mobile || '').toString().trim(),
          }),
        });
      } catch {
        // ignore patch errors; toast covers failure below
      }

      try {
        const addrRes = await fetchWithAuth('/api/v1/addresses/me');
        if (addrRes.ok) {
          const list = await addrRes.json();
          const items = Array.isArray(list?.items) ? list.items : [];
          const def =
            items.find((a: { is_default?: boolean }) => a?.is_default) || (items.length > 0 ? items[0] : null);
          const newZip = (zip || '').toString().trim();
          if (def && def.id) {
            if (newZip && newZip !== (def.postal_code || '')) {
              await fetchWithAuth(`/api/v1/addresses/me/${def.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: newZip }),
              });
            }
          } else if (newZip) {
            await fetchWithAuth('/api/v1/addresses/me', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ postal_code: newZip, is_default: true }),
            });
          }
        }
      } catch {
        // ignore address update failures; toast covers failure below
      }

      // Invalidate caches to reflect the changes
      void invalidateAddresses();
      toast.success('Account details updated');
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : 'Failed to update account details');
    } finally {
      setSavingAccount(false);
    }
  };

  return (
    <div className={embedded ? '' : 'min-h-screen'}>
      {!embedded && (
        <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">
                iNSTAiNSTRU
              </h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 hidden sm:block">
            <div className="container mx-auto px-8 lg:px-32 max-w-6xl pointer-events-none">
              <Link
                href="/instructor/dashboard"
                className="inline-flex items-center gap-1 text-[#7E22CE] pointer-events-auto"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'px-0 lg:px-0 py-0' : 'container mx-auto px-8 lg:px-32 py-8 max-w-6xl'}>
        <SectionHeroCard
          id={embedded ? 'account-first-card' : undefined}
          icon={Settings}
          title="Account settings"
          subtitle="Manage your personal details, security options, and platform preferences from one place."
        />

        <div className="bg-white rounded-lg border border-gray-200 p-6">
          {embedded ? (
            <>
              <button
                type="button"
                className="w-full flex items-center justify-between text-left"
                onClick={() => setOpenAccount((v) => !v)}
                aria-expanded={openAccount}
              >
                <div className="flex items-start gap-3 text-left">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <Settings className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <div>
                    <span className="block text-lg font-semibold text-gray-900">Account details</span>
                    <span className="mt-1 block text-sm text-gray-500">Update your contact info and preferred ZIP.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openAccount ? 'rotate-180' : ''}`} />
              </button>
              {openAccount && (
                <div className="mt-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Name</label>
                      <input
                        type="text"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/40"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Email</label>
                      <input
                        type="email"
                        value={email}
                        readOnly
                        disabled
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-100 text-gray-400 placeholder:text-gray-400 cursor-not-allowed pointer-events-none select-none"
                        style={{ WebkitTextFillColor: '#9CA3AF' }}
                        aria-readonly="true"
                        aria-disabled="true"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Mobile phone</label>
                      <input
                        type="text"
                        value={mobile}
                        onChange={(e) => setMobile(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/40"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">ZIP code</label>
                      <input
                        type="text"
                        value={zip}
                        onChange={(e) => setZip(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/40"
                      />
                    </div>
                    {accountLoading && <div className="col-span-full text-xs text-gray-500">Loading…</div>}
                  </div>
                  <div className="mt-4 flex justify-end">
                    <button
                      type="button"
                      onClick={handleSaveAccount}
                      disabled={savingAccount}
                      className="inline-flex items-center justify-center gap-2 rounded-md bg-[#7E22CE] text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingAccount ? 'Saving…' : 'Save changes'}
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Account Settings</h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-gray-100">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900">Profile Information</h3>
                    <p className="text-sm text-gray-500">Update your personal details and bio</p>
                  </div>
                  <Link href="/instructor/onboarding/account-setup" className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium">
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900">Skills & Pricing</h3>
                    <p className="text-sm text-gray-500">Manage your services and hourly rates</p>
                  </div>
                  <Link
                    href="/instructor/onboarding/skill-selection"
                    className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
                  >
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900">Service Areas</h3>
                    <p className="text-sm text-gray-500">Set where you can teach</p>
                  </div>
                  <Link
                    href="/instructor/onboarding/skill-selection"
                    className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
                  >
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900">Availability</h3>
                    <p className="text-sm text-gray-500">Adjust your schedule and booking availability</p>
                  </div>
                  <Link href="/instructor/availability" className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium">
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900">Notifications</h3>
                    <p className="text-sm text-gray-500">Choose how you want to be notified</p>
                  </div>
                  <button
                    type="button"
                    className="text-[#7E22CE] hover:text-[#6B1FA0] text-sm font-medium"
                    onClick={() => setOpenPreferences(true)}
                  >
                    Manage
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Referrals & rewards */}
        <div className="bg-white rounded-lg border border-gray-200 p-6 mt-6">
          {embedded ? (
            <>
              <button
                type="button"
                className="w-full flex items-start justify-between text-left"
                onClick={() => setOpenRefer((v) => !v)}
                aria-expanded={openRefer}
              >
                <div className="flex items-start gap-3 text-left">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <Gift className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <div>
                    <span className="block text-lg font-semibold text-gray-900">Refer instructors</span>
                    <span className="mt-1 block text-sm text-gray-500">Share your link to invite peers and earn rewards.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openRefer ? 'rotate-180' : ''}`} />
              </button>
              {openRefer && (
                <div className="mt-4">
                  <RewardsPanel
                    inviterName={fullName}
                    hideHeader
                    compactShare
                    hideShareIcon
                    minimalTabs
                    compactInvite
                    compactTabs
                  />
                </div>
              )}
            </>
          ) : (
            <>
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Gift className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Refer instructors</h2>
              </div>
            </div>
            <div className="mt-4">
              <RewardsPanel
                inviterName={fullName}
                hideHeader
                compactShare
                hideShareIcon
                  minimalTabs
                  compactInvite
                  compactTabs
                />
              </div>
            </>
          )}
        </div>

        {embedded && (
          <div className="bg-white rounded-lg border border-gray-200 p-6 mt-4">
            <button
              type="button"
              className="w-full flex items-center justify-between text-left"
              onClick={() => setOpenSecurity((v) => !v)}
              aria-expanded={openSecurity}
            >
              <div className="flex items-start gap-3 text-left">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Shield className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <div>
                  <span className="block text-lg font-semibold text-gray-900">Account security</span>
                  <span className="mt-1 block text-sm text-gray-500">Enable two-factor authentication for extra protection.</span>
                </div>
              </div>
              <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openSecurity ? 'rotate-180' : ''}`} />
            </button>
            {openSecurity && (
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-900">Two‑factor authentication</p>
                    <p className="text-xs text-gray-500">
                      Protect your account with a one‑time code from an authenticator app.
                    </p>
                  </div>
                  <button
                    type="button"
                    className={`px-3 py-1.5 rounded-md text-sm font-medium ${
                      tfaEnabled
                        ? 'border border-gray-300 text-gray-700 bg-white hover:bg-gray-50'
                        : 'bg-[#7E22CE] text-white hover:bg-[#6b1fb8]'
                    } `}
                    onClick={() => setShowTfaModal(true)}
                  >
                    {tfaEnabled ? 'Turn off' : 'Set up'}
                  </button>
                </div>
                {showTfaModal && (
                  <TfaModal
                    onClose={() => setShowTfaModal(false)}
                    onChanged={() => {
                      // Invalidate cache to refetch 2FA status
                      void invalidateTfaStatus();
                    }}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {embedded && (
          <div className="bg-white rounded-lg border border-gray-200 p-6 mt-4">
            <button
              type="button"
              className="w-full flex items-center justify-between text-left"
              onClick={() => setOpenStatus((v) => !v)}
              aria-expanded={openStatus}
            >
              <div className="flex items-start gap-3 text-left">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Power className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <div>
                  <span className="block text-lg font-semibold text-gray-900">Account status</span>
                  <span className="mt-1 block text-sm text-gray-500">Pause or close your instructor account if needed.</span>
                </div>
              </div>
              <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openStatus ? 'rotate-180' : ''}`} />
            </button>
            {openStatus && (
              <div className="mt-4 flex items-center justify-end gap-2 sm:gap-3 flex-wrap">
                <button
                  type="button"
                  onClick={() => setShowPauseModal(true)}
                  className="inline-flex items-center justify-center gap-2 rounded-md bg-white border border-purple-200 text-[#7E22CE] px-4 py-2 text-sm font-semibold transition hover:bg-purple-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2"
                >
                  Pause account
                </button>
                {showPauseModal && (
                  <PauseAccountModal
                    onClose={() => setShowPauseModal(false)}
                    onPaused={() => {
                      setShowPauseModal(false);
                    }}
                  />
                )}
                <button
                  type="button"
                  onClick={() => setShowDeleteModal(true)}
                  className="inline-flex items-center justify-center gap-2 rounded-md bg-[#7E22CE] text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2"
                >
                  Delete account
                </button>
                {showDeleteModal && (
                  <DeleteAccountModal
                    email={email}
                    onClose={() => setShowDeleteModal(false)}
                    onDeleted={() => {
                      setShowDeleteModal(false);
                    }}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {embedded && (
          <div className="bg-white rounded-lg border border-gray-200 p-6 mt-4">
            <button
              type="button"
              className="w-full flex items-center justify-between text-left"
              onClick={() => setOpenPassword((v) => !v)}
              aria-expanded={openPassword}
            >
              <div className="flex items-start gap-3 text-left">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <KeyRound className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <div>
                  <span className="block text-lg font-semibold text-gray-900">Password</span>
                  <span className="mt-1 block text-sm text-gray-500">Keep your login secure with a strong password.</span>
                </div>
              </div>
              <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openPassword ? 'rotate-180' : ''}`} />
            </button>
            {openPassword && (
              <div className="mt-4 flex items-center justify-end">
                <button
                  type="button"
                  onClick={() => setShowChangePassword(true)}
                  className="inline-flex items-center justify-center gap-2 rounded-md bg-[#7E22CE] text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-2"
                >
                  Change password
                </button>
                {showChangePassword && <ChangePasswordModal onClose={() => setShowChangePassword(false)} />}
              </div>
            )}
          </div>
        )}

        <div className="bg-white rounded-lg border border-gray-200 p-6 mt-6">
          {embedded ? (
            <>
              <button
                type="button"
                className="w-full flex items-center justify-between text-left"
                onClick={() => setOpenPreferences((v) => !v)}
                aria-expanded={openPreferences}
              >
                <div className="flex items-start gap-3 text-left">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <Settings className="w-6 h-6 text-[#7E22CE]" />
                  </div>
                  <div>
                    <span className="block text-lg font-semibold text-gray-900">Preferences</span>
                    <span className="mt-1 block text-sm text-gray-500">Choose how we contact you about lessons and updates.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openPreferences ? 'rotate-180' : ''}`} />
              </button>
              {openPreferences && (
                <div className="mt-4">
                  <div className="py-1">
                    <h3 className="text-sm font-medium text-gray-900 mb-2">Notifications</h3>
                    {renderNotificationPreferences()}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-gray-800 mb-4">Preferences</h2>
              <div>
                <h3 className="text-sm font-medium text-gray-900 mb-2">Notifications</h3>
                {renderNotificationPreferences()}
              </div>
            </>
          )}
        </div>

        {embedded && (
          <div className="bg-white rounded-lg border border-gray-200 p-6 mt-4">
            <button
              type="button"
              className="w-full flex items-center justify-between text-left"
              onClick={() => setOpenAccount((v) => !v)}
              aria-expanded={openAccount}
            >
              <div className="flex items-start gap-3 text-left">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Settings className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <div>
                  <span className="block text-lg font-semibold text-gray-900">About</span>
                  <span className="mt-1 block text-sm text-gray-500">Access legal resources and support information.</span>
                </div>
              </div>
              <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${openAccount ? 'rotate-180' : ''}`} />
            </button>
            {openAccount && (
              <div className="mt-3 text-sm text-gray-700 space-y-2">
                <div>
                  <a href="/acknowledgments" className="focus-link text-[#7E22CE] hover:text-[#7E22CE]">
                    Acknowledgments
                  </a>
                </div>
                <div>
                  <a href="/legal#privacy" className="focus-link text-[#7E22CE] hover:text-[#7E22CE]">
                    Privacy Policy
                  </a>
                </div>
                <div>
                  <a href="/legal#terms" className="focus-link text-[#7E22CE] hover:text-[#7E22CE]">
                    Terms &amp; Conditions
                  </a>
                </div>
                <div>
                  <a href="/support" className="focus-link text-[#7E22CE] hover:text-[#7E22CE]">
                    iNSTAiNSTRU support
                  </a>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default SettingsImpl;
