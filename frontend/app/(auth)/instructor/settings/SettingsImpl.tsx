'use client';

import Link from 'next/link';
import { memo, useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Info, SlidersHorizontal } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { ArrowLeft, Settings, ChevronDown, Shield, Power, UserRoundPen } from 'lucide-react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ToggleSwitch } from '@/components/ui/ToggleSwitch';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { extractApiErrorMessage } from '@/lib/apiErrors';
import type { AddressListResponse, ApiErrorResponse } from '@/features/shared/api/types';
import TfaModal from '@/components/security/TfaModal';
import ChangePasswordModal from '@/components/security/ChangePasswordModal';
import DeleteAccountModal from '@/components/security/DeleteAccountModal';
import PauseAccountModal from '@/components/security/PauseAccountModal';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { useSession } from '@/src/api/hooks/useSession';
import { queryKeys } from '@/src/api/queryKeys';
import { useUserAddresses, useInvalidateUserAddresses } from '@/hooks/queries/useUserAddresses';
import { useTfaStatus, useInvalidateTfaStatus } from '@/hooks/queries/useTfaStatus';
import {
  useInvalidateTrustedDevices,
  useRevokeAllTrustedDevices,
  useRevokeTrustedDevice,
  useTrustedDevices,
} from '@/hooks/queries/useTrustedDevices';
import { usePushNotifications } from '@/features/shared/hooks/usePushNotifications';
import { useNotificationPreferences } from '@/features/shared/hooks/useNotificationPreferences';
import { usePhoneVerificationFlow } from '@/features/shared/hooks/usePhoneVerificationFlow';
import { PhoneVerificationField } from '@/components/account/PhoneVerificationField';

const PREFERENCE_DEFAULTS = {
  lesson_updates: { email: true, push: true, sms: false },
  messages: { email: false, push: true, sms: false },
  reviews: { email: true, push: true, sms: false },
  learning_tips: { email: true, push: true, sms: false },
  system_updates: { email: true, push: false, sms: false },
  promotional: { email: false, push: false, sms: false },
} as const;

type PreferenceCategory = keyof typeof PREFERENCE_DEFAULTS;
type PreferenceChannel = keyof (typeof PREFERENCE_DEFAULTS)['lesson_updates'];
type OpenSection = 'account' | 'security' | 'status' | 'preferences' | 'about' | null;

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

const TRUSTED_DEVICE_DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

const PREFERENCE_ROWS: Array<{ category: PreferenceCategory; description: string }> = [
  { category: 'lesson_updates', description: 'Booking confirmations, reminders, cancellations' },
  { category: 'messages', description: 'Direct messages from students' },
  { category: 'reviews', description: 'New reviews, review responses' },
  { category: 'learning_tips', description: 'Platform tips and learning resources' },
  { category: 'system_updates', description: 'Important platform notices and policy changes' },
  { category: 'promotional', description: 'Discounts, special offers, new features' },
];

type PreferenceToggleProps = {
  category: PreferenceCategory;
  channel: PreferenceChannel;
  checked: boolean;
  disabled?: boolean;
  title?: string | undefined;
  onToggle: (category: PreferenceCategory, channel: PreferenceChannel, checked: boolean) => void;
};

const PreferenceToggle = memo(function PreferenceToggle({
  category,
  channel,
  checked,
  disabled = false,
  title,
  onToggle,
}: PreferenceToggleProps) {
  const ariaLabel = `${CATEGORY_LABELS[category]} ${CHANNEL_LABELS[channel]} notifications`;
  const handleChange = useCallback(() => {
    onToggle(category, channel, checked);
  }, [category, channel, checked, onToggle]);

  return (
    <ToggleSwitch
      checked={checked}
      onChange={handleChange}
      disabled={disabled}
      ariaLabel={ariaLabel}
      {...(title ? { title } : {})}
    />
  );
});

type NotificationPreferenceRowProps = {
  category: PreferenceCategory;
  description: string;
  emailChecked: boolean;
  smsChecked: boolean;
  pushChecked: boolean;
  emailDisabled?: boolean;
  smsDisabled?: boolean;
  pushDisabled?: boolean;
  emailTitle?: string | undefined;
  smsTitle?: string | undefined;
  pushTitle?: string | undefined;
  onToggle: (category: PreferenceCategory, channel: PreferenceChannel, checked: boolean) => void;
};

type SaveAccountMutationVariables = {
  firstName: string;
  zip: string;
};

type SaveAccountMutationResult = {
  firstName: string;
  zip: string;
  attemptedAddressSync: boolean;
  addressSyncFailed: boolean;
};

const NotificationPreferenceRow = memo(function NotificationPreferenceRow({
  category,
  description,
  emailChecked,
  smsChecked,
  pushChecked,
  emailDisabled = false,
  smsDisabled = false,
  pushDisabled = false,
  emailTitle,
  smsTitle,
  pushTitle,
  onToggle,
}: NotificationPreferenceRowProps) {
  return (
    <div className="grid grid-cols-4 gap-4 items-start py-2">
      <div>
        <div className="font-medium text-gray-900 dark:text-gray-100">{CATEGORY_LABELS[category]}</div>
        <div className="text-xs text-gray-500 dark:text-gray-400">{description}</div>
      </div>
      <div className="flex justify-center">
        <PreferenceToggle
          category={category}
          channel="email"
          checked={emailChecked}
          disabled={emailDisabled}
          title={emailTitle}
          onToggle={onToggle}
        />
      </div>
      <div className="flex justify-center">
        <PreferenceToggle
          category={category}
          channel="sms"
          checked={smsChecked}
          disabled={smsDisabled}
          title={smsTitle}
          onToggle={onToggle}
        />
      </div>
      <div className="flex justify-center">
        <PreferenceToggle
          category={category}
          channel="push"
          checked={pushChecked}
          disabled={pushDisabled}
          title={pushTitle}
          onToggle={onToggle}
        />
      </div>
    </div>
  );
});

function formatTrustedDeviceDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return 'Unknown';
  }
  return TRUSTED_DEVICE_DATE_FORMATTER.format(parsed);
}

export function SettingsImpl({ embedded = false }: { embedded?: boolean }) {
  const [openSection, setOpenSection] = useState<OpenSection>(null);
  const [showTfaModal, setShowTfaModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showPauseModal, setShowPauseModal] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [firstNameDraft, setFirstNameDraft] = useState<string | null>(null);
  const [zipDraft, setZipDraft] = useState<string | null>(null);
  const [accountFirstNameError, setAccountFirstNameError] = useState('');

  // React Query hooks for data fetching (replaces useEffect fetches)
  const shouldLoadTfaStatus = embedded ? openSection === 'security' : true;
  const { data: tfaStatus, isLoading: tfaStatusLoading } = useTfaStatus(shouldLoadTfaStatus);
  const shouldLoadTrustedDevices = shouldLoadTfaStatus && tfaStatus?.enabled === true;
  const { data: trustedDevicesData, isLoading: trustedDevicesLoading } =
    useTrustedDevices(shouldLoadTrustedDevices);
  const { data: userData, isLoading: userLoading } = useSession();
  const { data: addressData, isLoading: addressLoading } = useUserAddresses(embedded);
  const queryClient = useQueryClient();
  const invalidateTfaStatus = useInvalidateTfaStatus();
  const invalidateTrustedDevices = useInvalidateTrustedDevices();
  const invalidateAddresses = useInvalidateUserAddresses();
  const revokeTrustedDevice = useRevokeTrustedDevice();
  const revokeAllTrustedDevices = useRevokeAllTrustedDevices();
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
    isPreferenceUpdating,
    updatePreference,
  } = useNotificationPreferences();
  const phoneFlow = usePhoneVerificationFlow({
    initialPhoneNumber: userData?.phone ?? '',
  });
  const phoneNumber = phoneFlow.phoneNumber;
  const phoneVerified = phoneFlow.phoneVerified;
  const phoneLoading = phoneFlow.phoneLoading;

  // Derived state from hooks
  const tfaEnabled = tfaStatus?.enabled ?? null;
  const tfaToggleChecked = tfaEnabled === true;
  const tfaToggleDisabled = tfaStatusLoading || showTfaModal;
  const trustedDevices = trustedDevicesData?.items ?? [];
  const trustedDevicesBusy = revokeTrustedDevice.isPending || revokeAllTrustedDevices.isPending;
  const tfaStateLabel = tfaStatusLoading ? 'Loading…' : tfaToggleChecked ? 'Enabled' : 'Off';
  const tfaStateSubtitle = tfaStatusLoading
    ? 'Checking your current two-factor authentication status'
    : tfaToggleChecked
      ? 'Your account is protected with two-factor authentication'
      : 'Add an extra layer of security with an authenticator app';
  const accountLoading = userLoading || addressLoading || phoneLoading;
  const accountDefaults = {
    firstName: (userData?.first_name || '').toString().trim(),
    lastName: (userData?.last_name || '').toString().trim(),
    email: (userData?.email || '').toString(),
    zip: (
      (Array.isArray(addressData?.items)
        ? (addressData.items.find((address) => address.is_default) || addressData.items[0] || null)?.postal_code
        : null) || userData?.zip_code || ''
    ).toString(),
  };
  const firstName = firstNameDraft ?? accountDefaults.firstName;
  const lastName = accountDefaults.lastName;
  const email = accountDefaults.email;
  const zip = zipDraft ?? accountDefaults.zip;
  const pushDisabled = !pushSupported || pushLoading || pushPermission === 'denied';
  const preferencesDisabled = preferencesLoading;
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
  const toggleSection = useCallback((section: Exclude<OpenSection, null>) => {
    setOpenSection((prev) => (prev === section ? null : section));
  }, []);
  const openTfaModal = useCallback(() => {
    if (tfaToggleDisabled) return;
    setShowTfaModal(true);
  }, [tfaToggleDisabled]);

  const handleRevokeTrustedDevice = async (deviceId: string) => {
    try {
      const result = await revokeTrustedDevice.mutateAsync(deviceId);
      toast.success(result.message);
    } catch {
      toast.error('Failed to revoke trusted device.');
    }
  };

  const handleRevokeAllTrustedDevices = async () => {
    try {
      const result = await revokeAllTrustedDevices.mutateAsync();
      toast.success(result.message);
    } catch {
      toast.error('Failed to revoke trusted devices.');
    }
  };

  const handlePushToggle = async (enabled: boolean) => {
    if (enabled) {
      await enablePush();
    } else {
      await disablePush();
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
      {!pushSupported && <p className="text-gray-500 dark:text-gray-400">Push notifications are not supported in this browser.</p>}
      {pushPermission === 'denied' && (
        <p className="text-amber-600">Push notifications are currently blocked. Enable them in your browser settings to continue.</p>
      )}
      {pushLoading && <p className="text-gray-500 dark:text-gray-400">Updating push notifications…</p>}
      {pushError && <p className="text-red-600">{pushError}</p>}
    </div>
  );

  const getPreferenceValue = (category: PreferenceCategory, channel: PreferenceChannel) => {
    const fallback = PREFERENCE_DEFAULTS[category][channel];
    return preferences?.[category]?.[channel] ?? fallback;
  };
  const handlePreferenceToggle = useCallback(
    (category: PreferenceCategory, channel: PreferenceChannel, checked: boolean) => {
      updatePreference(category, channel, !checked);
    },
    [updatePreference]
  );

  const renderNotificationPreferences = () => {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Push notifications on this device</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Enable push notifications in this browser to receive alerts.
              </p>
            </div>
            {renderPushToggle()}
          </div>
          {renderPushStatus()}
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4 pb-3 border-b border-gray-200 dark:border-gray-700">
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Notification Type</div>
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300 text-center">Email</div>
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300 text-center">SMS</div>
            <div className="text-sm font-medium text-gray-700 dark:text-gray-300 text-center">Push</div>
          </div>
          {PREFERENCE_ROWS.map(({ category, description }) => {
            const emailUpdating = isPreferenceUpdating(category, 'email');
            const smsUpdating = isPreferenceUpdating(category, 'sms');
            const pushUpdating = isPreferenceUpdating(category, 'push');
            const messagePushLocked = category === 'messages';

            return (
              <NotificationPreferenceRow
                key={category}
                category={category}
                description={description}
                emailChecked={getPreferenceValue(category, 'email')}
                smsChecked={getPreferenceValue(category, 'sms')}
                pushChecked={getPreferenceValue(category, 'push')}
                emailDisabled={preferencesDisabled || emailUpdating}
                smsDisabled={smsPreferenceDisabled || smsUpdating}
                pushDisabled={messagePushLocked ? true : pushPreferenceDisabled || pushUpdating}
                smsTitle={smsPreferenceTitle}
                pushTitle={messagePushLocked ? 'Push notifications for messages are required.' : pushPreferenceTitle}
                onToggle={handlePreferenceToggle}
              />
            );
          })}
        </div>
      </div>
    );
  };

  const renderSecurityContent = () => (
    <div className="mt-4">
      <div className="flex items-start justify-between gap-4 py-1">
        <div className="max-w-xl">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Two-factor authentication</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {tfaStateSubtitle}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span
            className={`text-sm font-medium ${
              tfaToggleChecked ? 'text-(--color-brand-dark)' : 'text-gray-600 dark:text-gray-400'
            }`}
          >
            {tfaStateLabel}
          </span>
          <ToggleSwitch
            checked={tfaToggleChecked}
            onChange={openTfaModal}
            disabled={tfaToggleDisabled}
            ariaLabel="Two-factor authentication"
            title={tfaStatusLoading ? 'Loading two-factor authentication status' : 'Two-factor authentication'}
          />
        </div>
      </div>
      <div className="my-4 border-t border-gray-100 dark:border-gray-700" />
      <div className="flex items-start justify-between gap-4 py-1">
        <div className="max-w-xl">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Password</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Update your password to keep your login secure.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowChangePassword(true)}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-(--color-brand-dark) text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-dark) focus-visible:ring-offset-2 insta-primary-btn"
        >
          Change password
        </button>
      </div>
      <div className="my-4 border-t border-gray-100 dark:border-gray-700" />
      <div className="space-y-3 py-1">
        <div className="flex items-start justify-between gap-4">
          <div className="max-w-xl">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Trusted devices</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {tfaToggleChecked
                ? 'Browsers you trust can skip the two-factor prompt for 30 days.'
                : 'Enable two-factor authentication to manage trusted browsers.'}
            </p>
          </div>
          {tfaToggleChecked && trustedDevices.length > 0 ? (
            <button
              type="button"
              onClick={() => void handleRevokeAllTrustedDevices()}
              disabled={trustedDevicesBusy}
              className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 transition hover:bg-gray-50 dark:hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Revoke all
            </button>
          ) : null}
        </div>

        {tfaStatusLoading ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading trusted devices…</p>
        ) : !tfaToggleChecked ? (
          <div className="rounded-xl border border-dashed border-gray-200 dark:border-gray-700 px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
            Turn on two-factor authentication first. Then you can trust a browser during login and manage it here.
          </div>
        ) : trustedDevicesLoading ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading trusted devices…</p>
        ) : trustedDevices.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-200 dark:border-gray-700 px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
            No trusted devices yet. Choose &quot;Trust this browser&quot; the next time you complete two-factor authentication on a device you own.
          </div>
        ) : (
          <div className="space-y-3">
            {trustedDevices.map((device) => (
              <div
                key={device.id}
                className="flex items-start justify-between gap-4 rounded-xl border border-gray-100 dark:border-gray-700 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{device.device_name}</p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Last used {formatTrustedDeviceDate(device.last_used_at)}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Expires {formatTrustedDeviceDate(device.expires_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleRevokeTrustedDevice(device.id)}
                  disabled={trustedDevicesBusy}
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm font-semibold text-gray-700 dark:text-gray-200 transition hover:bg-gray-50 dark:hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Revoke
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  const renderAccountStatusContent = () => (
    <div className="mt-4 flex items-center justify-end gap-2 sm:gap-3 flex-wrap">
      <button
        type="button"
        onClick={() => setShowPauseModal(true)}
        className="inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-dark) focus-visible:ring-offset-2 insta-secondary-btn"
      >
        Pause account
      </button>
      <button
        type="button"
        onClick={() => setShowDeleteModal(true)}
        className="inline-flex items-center justify-center gap-2 rounded-md bg-(--color-brand-dark) text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-dark) focus-visible:ring-offset-2 insta-primary-btn"
      >
        Delete account
      </button>
    </div>
  );

  const saveAccountMutation = useMutation<
    SaveAccountMutationResult,
    Error,
    SaveAccountMutationVariables
  >({
    mutationFn: async ({
      firstName: mutationFirstName,
      zip: mutationZip,
    }): Promise<SaveAccountMutationResult> => {
      const normalizedSavedZip = accountDefaults.zip.trim();
      const attemptedAddressSync = mutationZip !== normalizedSavedZip;

      const userResponse = await fetchWithAuth(API_ENDPOINTS.ME, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: mutationFirstName,
          zip_code: mutationZip,
        }),
      });
      if (!userResponse.ok) {
        const errorBody = (await userResponse.json()) as ApiErrorResponse;
        const message = extractApiErrorMessage(errorBody, 'Failed to update account details');
        throw new Error(message);
      }

      let addressSyncFailed = false;
      if (attemptedAddressSync) {
        try {
          const addrRes = await fetchWithAuth('/api/v1/addresses/me');
          if (!addrRes.ok) {
            addressSyncFailed = true;
          } else {
            const list = (await addrRes.json()) as AddressListResponse;
            const items = Array.isArray(list?.items) ? list.items : [];
            const defaultAddress =
              items.find((item) => item.is_default) || (items.length > 0 ? items[0] : null);

            if (defaultAddress?.id) {
              if (mutationZip !== (defaultAddress.postal_code || '')) {
                const patchResponse = await fetchWithAuth(`/api/v1/addresses/me/${defaultAddress.id}`, {
                  method: 'PATCH',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ postal_code: mutationZip }),
                });
                if (!patchResponse.ok) {
                  addressSyncFailed = true;
                }
              }
            } else {
              const createResponse = await fetchWithAuth('/api/v1/addresses/me', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ postal_code: mutationZip, is_default: true }),
              });
              if (!createResponse.ok) {
                addressSyncFailed = true;
              }
            }
          }
        } catch {
          addressSyncFailed = true;
        }
      }

      return {
        firstName: mutationFirstName,
        zip: mutationZip,
        attemptedAddressSync,
        addressSyncFailed,
      };
    },
    onSuccess: async ({ firstName: savedFirstName, zip: savedZip, attemptedAddressSync, addressSyncFailed }) => {
      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: queryKeys.auth.me }),
        queryClient.invalidateQueries({ queryKey: queryKeys.instructors.me }),
        Promise.resolve(invalidateAddresses()),
      ]);
      setFirstNameDraft(savedFirstName);
      setZipDraft(savedZip);
      toast.success(
        attemptedAddressSync && addressSyncFailed
          ? 'Profile updated, but address failed to save. Please try again.'
          : 'Account details updated'
      );
    },
    onError: (error) => {
      toast.error(error.message);
    },
  });

  const handleSaveAccount = async () => {
    const trimmedFirstName = firstName.trim();
    const newZip = zip.trim();
    if (!trimmedFirstName) {
      setAccountFirstNameError('First name is required.');
      toast.error('First name is required.');
      return;
    }
    if (!newZip) {
      toast.error('ZIP code is required.');
      return;
    }

    setAccountFirstNameError('');
    try {
      await saveAccountMutation.mutateAsync({
        firstName: trimmedFirstName,
        zip: newZip,
      });
    } catch {
      // Toasts are handled by the mutation callbacks.
    }
  };

  return (
    <div className={embedded ? 'insta-dashboard-page' : 'min-h-screen insta-dashboard-page'}>
      {!embedded && (
        <header className="relative px-4 sm:px-6 py-4 insta-dashboard-header">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="text-3xl font-bold text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300 transition-colors cursor-pointer pl-0 sm:pl-4">
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
                className="inline-flex items-center gap-1 text-(--color-brand-dark) pointer-events-auto"
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

        <div className="insta-dashboard-accordion-stack">
        <div className="p-6 insta-surface-card">
          {embedded ? (
            <>
              <button
                type="button"
                className="insta-dashboard-accordion-trigger"
                onClick={() => toggleSection('account')}
                aria-expanded={openSection === 'account'}
              >
                <div className="insta-dashboard-accordion-leading">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <UserRoundPen className="w-6 h-6 text-(--color-brand-dark)" />
                  </div>
                  <div>
                    <span className="insta-dashboard-accordion-title">Account details</span>
                    <span className="insta-dashboard-accordion-subtitle">Update your contact info and preferred ZIP.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 dark:text-gray-400 transition-transform ${openSection === 'account' ? 'rotate-180' : ''}`} />
              </button>
              {openSection === 'account' && (
                <div className="mt-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <label htmlFor="settings-first-name" className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                        First name
                      </label>
                      <input
                        id="settings-first-name"
                        type="text"
                        value={firstName}
                        onChange={(e) => {
                          setFirstNameDraft(e.target.value);
                          setAccountFirstNameError('');
                        }}
                        className="w-full px-3 py-2 insta-form-input focus:outline-none focus:ring-2 focus:ring-(--color-brand-dark)/40"
                      />
                      {accountFirstNameError && (
                        <p className="mt-2 text-xs text-red-600 dark:text-red-400" role="alert">
                          {accountFirstNameError}
                        </p>
                      )}
                    </div>
                    <div>
                      <label htmlFor="settings-last-name" className="mb-1 block text-xs text-gray-500 dark:text-gray-400">
                        Last name · verified
                      </label>
                      <input
                        id="settings-last-name"
                        type="text"
                        value={lastName}
                        readOnly
                        disabled
                        className="w-full px-3 py-2 insta-form-input insta-form-input-readonly cursor-not-allowed pointer-events-none select-none"
                        aria-readonly="true"
                        aria-disabled="true"
                      />
                    </div>
                    <div>
                      <label htmlFor="settings-email" className="mb-1 block text-xs text-gray-500 dark:text-gray-400">
                        Email · verified
                      </label>
                      <input
                        id="settings-email"
                        type="email"
                        value={email}
                        readOnly
                        disabled
                        className="w-full px-3 py-2 insta-form-input insta-form-input-readonly cursor-not-allowed pointer-events-none select-none"
                        aria-readonly="true"
                        aria-disabled="true"
                      />
                    </div>
                    <div>
                      <label htmlFor="settings-zip" className="mb-1 block text-xs text-gray-600 dark:text-gray-400">
                        ZIP code
                      </label>
                      <input
                        id="settings-zip"
                        type="text"
                        value={zip}
                        onChange={(e) => setZipDraft(e.target.value)}
                        className="w-full px-3 py-2 insta-form-input focus:outline-none focus:ring-2 focus:ring-(--color-brand-dark)/40"
                      />
                    </div>
                    <div className="space-y-3 sm:col-span-2">
                      <PhoneVerificationField
                        flow={phoneFlow}
                        inputId="settings-phone"
                        codeInputId="settings-phone-code"
                        label="Phone number"
                      />
                    </div>
                    {accountLoading ? (
                      <div className="col-span-full text-xs text-gray-500 dark:text-gray-400">Loading…</div>
                    ) : null}
                  </div>
                  <div className="mt-4 flex justify-end">
                    <button
                      type="button"
                      onClick={handleSaveAccount}
                      disabled={saveAccountMutation.isPending}
                      className="inline-flex items-center justify-center gap-2 rounded-md bg-(--color-brand-dark) text-white px-4 py-2 text-sm font-semibold transition hover:bg-[#6b1fb8] focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-brand-dark) focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 insta-primary-btn"
                    >
                      {saveAccountMutation.isPending ? 'Saving…' : 'Save changes'}
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">Account Settings</h2>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-gray-700">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Profile Information</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Update your personal details and bio</p>
                  </div>
                  <Link href="/instructor/onboarding/account-setup" className="text-(--color-brand-dark) hover:text-[#6B1FA0] text-sm font-medium">
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-gray-700">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Skills & Pricing</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Manage your services and hourly rates</p>
                  </div>
                  <Link
                    href="/instructor/onboarding/skill-selection"
                    className="text-(--color-brand-dark) hover:text-[#6B1FA0] text-sm font-medium"
                  >
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-gray-700">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Service Areas</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Set where you can teach</p>
                  </div>
                  <Link
                    href="/instructor/onboarding/skill-selection"
                    className="text-(--color-brand-dark) hover:text-[#6B1FA0] text-sm font-medium"
                  >
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-gray-700">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Availability</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Adjust your schedule and booking availability</p>
                  </div>
                  <Link href="/instructor/availability" className="text-(--color-brand-dark) hover:text-[#6B1FA0] text-sm font-medium">
                    Edit
                  </Link>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-gray-100 dark:border-gray-700">
                  <div>
                    <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Notifications</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Choose how you want to be notified</p>
                  </div>
                  <button
                    type="button"
                    className="text-(--color-brand-dark) hover:text-[#6B1FA0] text-sm font-medium"
                    onClick={() => setOpenSection('preferences')}
                  >
                    Manage
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
        <div className="p-6 insta-surface-card">
          {embedded ? (
            <>
              <button
                type="button"
                className="insta-dashboard-accordion-trigger"
                onClick={() => toggleSection('security')}
                aria-expanded={openSection === 'security'}
              >
                <div className="insta-dashboard-accordion-leading">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <Shield className="w-6 h-6 text-(--color-brand-dark)" />
                  </div>
                  <div>
                    <span className="insta-dashboard-accordion-title">Security</span>
                    <span className="insta-dashboard-accordion-subtitle">Keep your account safe</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 dark:text-gray-400 transition-transform ${openSection === 'security' ? 'rotate-180' : ''}`} />
              </button>
              {openSection === 'security' && renderSecurityContent()}
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-1">Security</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Keep your account safe</p>
              {renderSecurityContent()}
            </>
          )}
        </div>

        <div className="p-6 insta-surface-card">
          {embedded ? (
            <>
              <button
                type="button"
                className="insta-dashboard-accordion-trigger"
                onClick={() => toggleSection('status')}
                aria-expanded={openSection === 'status'}
              >
                <div className="insta-dashboard-accordion-leading">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <Power className="w-6 h-6 text-(--color-brand-dark)" />
                  </div>
                  <div>
                    <span className="insta-dashboard-accordion-title">Account status</span>
                    <span className="insta-dashboard-accordion-subtitle">Pause or close your instructor account if needed.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 dark:text-gray-400 transition-transform ${openSection === 'status' ? 'rotate-180' : ''}`} />
              </button>
              {openSection === 'status' && renderAccountStatusContent()}
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-1">Account Status</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Pause or close your instructor account if needed.</p>
              {renderAccountStatusContent()}
            </>
          )}
        </div>

        <div className="p-6 insta-surface-card">
          {embedded ? (
            <>
              <button
                type="button"
                className="insta-dashboard-accordion-trigger"
                onClick={() => toggleSection('preferences')}
                aria-expanded={openSection === 'preferences'}
              >
                <div className="insta-dashboard-accordion-leading">
                  <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                    <SlidersHorizontal className="w-6 h-6 text-(--color-brand-dark)" />
                  </div>
                  <div>
                    <span className="insta-dashboard-accordion-title">Preferences</span>
                    <span className="insta-dashboard-accordion-subtitle">Choose how we contact you about lessons and updates.</span>
                  </div>
                </div>
                <ChevronDown className={`w-5 h-5 text-gray-600 dark:text-gray-400 transition-transform ${openSection === 'preferences' ? 'rotate-180' : ''}`} />
              </button>
              {openSection === 'preferences' && (
                <div className="mt-4">
                  <div className="py-1">
                    <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">Notifications</h3>
                    {renderNotificationPreferences()}
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4">Preferences</h2>
              <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">Notifications</h3>
                {renderNotificationPreferences()}
              </div>
            </>
          )}
        </div>

        {embedded && (
          <div className="p-6 insta-surface-card">
            <button
              type="button"
              className="insta-dashboard-accordion-trigger"
              onClick={() => toggleSection('about')}
              aria-expanded={openSection === 'about'}
            >
              <div className="insta-dashboard-accordion-leading">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Info className="w-6 h-6 text-(--color-brand-dark)" />
                </div>
                <div>
                  <span className="insta-dashboard-accordion-title">About</span>
                  <span className="insta-dashboard-accordion-subtitle">Access legal resources and support information.</span>
                </div>
              </div>
              <ChevronDown className={`w-5 h-5 text-gray-600 dark:text-gray-400 transition-transform ${openSection === 'about' ? 'rotate-180' : ''}`} />
            </button>
            {openSection === 'about' && (
              <div className="mt-5 text-sm text-gray-700 dark:text-gray-300 space-y-3">
                <div>
                  <a href="/legal#privacy" className="focus-link text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300">
                    Privacy Policy
                  </a>
                </div>
                <div>
                  <a href="/legal#terms" className="focus-link text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300">
                    Terms &amp; Conditions
                  </a>
                </div>
                <div>
                  <a href="/support" className="focus-link text-(--color-brand-dark) hover:text-purple-900 dark:hover:text-purple-300">
                    Support
                  </a>
                </div>
              </div>
            )}
          </div>
        )}
        {showTfaModal && (
          <TfaModal
            onClose={() => setShowTfaModal(false)}
            onChanged={() => {
              void invalidateTfaStatus();
              void invalidateTrustedDevices();
            }}
          />
        )}
        {showPauseModal && (
          <PauseAccountModal
            onClose={() => setShowPauseModal(false)}
            onPaused={() => {
              setShowPauseModal(false);
            }}
          />
        )}
        {showDeleteModal && (
          <DeleteAccountModal
            email={email}
            onClose={() => setShowDeleteModal(false)}
            onDeleted={() => {
              setShowDeleteModal(false);
            }}
          />
        )}
        {showChangePassword && <ChangePasswordModal onClose={() => setShowChangePassword(false)} />}
        </div>
      </div>
    </div>
  );
}

export default SettingsImpl;
