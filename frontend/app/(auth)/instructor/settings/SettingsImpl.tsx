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

const RewardsPanel = dynamic(() => import('@/features/referrals/RewardsPanel'), { ssr: false });

const PREFERENCE_DEFAULTS = {
  lesson_updates: { email: true, push: true, sms: false },
  messages: { email: false, push: true, sms: false },
  promotional: { email: false, push: false, sms: false },
} as const;

type PreferenceCategory = keyof typeof PREFERENCE_DEFAULTS;
type PreferenceChannel = keyof (typeof PREFERENCE_DEFAULTS)['lesson_updates'];

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

  const handlePushToggle = async (enabled: boolean) => {
    if (enabled) {
      await enablePush();
    } else {
      await disablePush();
    }
  };

  const renderPushToggle = () => (
    <input
      type="checkbox"
      checked={pushEnabled}
      onChange={(event) => void handlePushToggle(event.target.checked)}
      disabled={pushDisabled}
      title={pushToggleTitle}
      aria-label="Push notifications"
      className={pushDisabled ? 'cursor-not-allowed' : undefined}
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

  const renderPreferenceToggle = (
    category: PreferenceCategory,
    channel: PreferenceChannel,
    options?: { disabled?: boolean; title?: string }
  ) => {
    const isDisabled = options?.disabled ?? preferencesDisabled;
    return (
      <input
        type="checkbox"
        checked={getPreferenceValue(category, channel)}
        onChange={(event) => updatePreference(category, channel, event.target.checked)}
        disabled={isDisabled}
        title={options?.title}
        aria-label={`${category} ${channel} notifications`}
        className={isDisabled ? 'cursor-not-allowed' : undefined}
      />
    );
  };

  const renderNotificationPreferences = () => {
    const pushPreferenceOptions = pushPreferenceTitle
      ? { disabled: pushPreferenceDisabled, title: pushPreferenceTitle }
      : { disabled: pushPreferenceDisabled };

    return (
      <div className="space-y-4">
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
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="font-medium pr-6">Form of Communication</th>
              <th className="font-medium pr-6">Email</th>
              <th className="font-medium pr-6">SMS</th>
              <th className="font-medium">Push Notification</th>
            </tr>
          </thead>
          <tbody className="align-top">
            <tr className="text-gray-800">
              <td className="py-2 pr-6">Lesson updates</td>
              <td className="pr-6">
                {renderPreferenceToggle('lesson_updates', 'email')}
              </td>
              <td className="pr-6">
                {renderPreferenceToggle('lesson_updates', 'sms')}
              </td>
              <td>
                {renderPreferenceToggle('lesson_updates', 'push', pushPreferenceOptions)}
              </td>
            </tr>
            <tr className="text-gray-800">
              <td className="py-2 pr-6">Promotional emails and notifications</td>
              <td className="pr-6">
                {renderPreferenceToggle('promotional', 'email')}
              </td>
              <td className="pr-6">
                {renderPreferenceToggle('promotional', 'sms')}
              </td>
              <td>
                {renderPreferenceToggle('promotional', 'push', pushPreferenceOptions)}
              </td>
            </tr>
            <tr className="text-gray-800">
              <td className="py-2 pr-6">Messages</td>
              <td className="pr-6">
                {renderPreferenceToggle('messages', 'email')}
              </td>
              <td className="pr-6">
                {renderPreferenceToggle('messages', 'sms')}
              </td>
              <td>
                {renderPreferenceToggle('messages', 'push', {
                  disabled: true,
                  title: 'Push notifications for messages are required.',
                })}
              </td>
            </tr>
          </tbody>
        </table>
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
