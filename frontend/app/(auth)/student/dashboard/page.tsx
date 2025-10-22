// frontend/app/dashboard/student/page.tsx
'use client';

import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Heart, User, CreditCard, Bell, Eye, EyeOff, X, Award, Zap, Star, BookOpen, Calendar, Target, Globe, Lock, CheckCircle, Gift } from 'lucide-react';
import { ProfilePictureUpload } from '@/components/user/ProfilePictureUpload';
import { UserAvatar } from '@/components/user/UserAvatar';
import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';
import { logger } from '@/lib/logger';
import { at } from '@/lib/ts/safe';
import { useAuth, type User as AuthUser } from '@/features/shared/hooks/useAuth';
import { hasRole } from '@/features/shared/hooks/useAuth.helpers';
import { RoleName } from '@/types/enums';
import { fetchAPI, fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { toast } from 'sonner';
import { favoritesApi } from '@/services/api/favorites';
import type { FavoritesListResponse } from '@/features/shared/api/types';
import { getServiceAreaDisplay } from '@/lib/profileServiceAreas';
import RewardsPanel from '@/features/referrals/RewardsPanel';
// Use dashboard-specific saved address shape (differs from common Address)
type SavedAddress = {
  id: string;
  label?: string;
  street_1?: string;
  street_2?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  is_default?: boolean;
};
import UserProfileDropdown from '@/components/UserProfileDropdown';
import BillingTab from '@/components/student/BillingTab';
import { getActivityBackground } from '@/lib/services/assetService';

/**
 * StudentDashboard Component
 *
 * Main dashboard interface for students. Provides quick access to instructor search,
 * booking management, and displays upcoming sessions.
 *
 * Features:
 * - Authentication verification and role-based redirect
 * - Quick action cards for common tasks
 * - Upcoming sessions preview (shows up to 3)
 * - Loading and empty states
 * - Responsive design
 *
 * @component
 * @example
 * ```tsx
 * // This is a page component, typically accessed via routing
 * // Route: /student/dashboard
 * ```
 */
// Disable prerendering; this page depends on searchParams and auth session
export const dynamic = 'force-dynamic';

function StudentDashboardContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { logout } = useAuth();
  const [isStatsVisible, setIsStatsVisible] = useState(true);
  const [showDelete, setShowDelete] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [showTfaModal, setShowTfaModal] = useState(false);
  const [addresses, setAddresses] = useState<SavedAddress[] | null>(null);
  const [isLoadingAddresses, setIsLoadingAddresses] = useState(false);
  const [showAddressModal, setShowAddressModal] = useState<null | { mode: 'create' } | { mode: 'edit'; address: SavedAddress }>(null);
  const [tfaStatus, setTfaStatus] = useState<{ enabled: boolean; verified_at?: string | null; last_used_at?: string | null } | null>(null);
  const [, setProfilePhoto] = useState<string | null>(null);
  const [showEditProfile, setShowEditProfile] = useState(false);
  const [showAchievementsModal, setShowAchievementsModal] = useState(false);

  const tabs = useMemo(
    () => [
      { key: 'profile', label: 'Profile', icon: User },
      { key: 'billing', label: 'Billing', icon: CreditCard },
      { key: 'notifications', label: 'Notifications', icon: Bell },
      { key: 'favorites', label: 'Favorites', icon: Heart },
      { key: 'rewards', label: 'Rewards', icon: Gift },
    ] as const,
    []
  );

  type TabKey = (typeof tabs)[number]['key'];
  const [activeTab, setActiveTab] = useState<TabKey>('profile');

  // Fetch user data with React Query
  const {
    data: userData,
    isLoading: isLoadingUser,
    error: userError,
    refetch: refetchUserData,
  } = useQuery<AuthUser>({
    queryKey: queryKeys.user,
    queryFn: queryFn('/auth/me', { requireAuth: true }),
    staleTime: CACHE_TIMES.SESSION, // Session-long cache
    retry: false,
  });

  // Debug user data
  useEffect(() => {
    if (userData) {
      logger.debug('User data loaded');
    }
  }, [userData]);

  const isLoading = isLoadingUser;

  // Favorites data (loaded lazily when the tab is active)
  const {
    data: favoritesData,
    isLoading: isLoadingFavorites,
    error: favoritesError,
    refetch: refetchFavorites,
  } = useQuery<unknown, Error, FavoritesListResponse>({
    queryKey: ['favorites'],
    queryFn: () => favoritesApi.list() as unknown as Promise<unknown>,
    select: (d) => d as FavoritesListResponse,
    enabled: activeTab === 'favorites',
    // Always refetch when navigating to the tab to avoid stale cache view
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
  });

  // Sync active tab with URL (?tab=...)
  useEffect(() => {
    const initial = searchParams.get('tab');
    if (initial && tabs.some(t => t.key === (initial as TabKey))) {
      setActiveTab(initial as TabKey);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-time initialization with stable inputs
  }, []);

  // Handle authentication and role-based redirects
  useEffect(() => {
    if (userError || (!isLoadingUser && !userData)) {
      logger.warn('No user data, redirecting to login');
      router.push('/login');
      return;
    }

    if (userData && !hasRole(userData, RoleName.STUDENT)) {
      logger.info('User is not a student, redirecting to instructor dashboard', {
        userId: userData.id,
        roles: userData.roles,
      });
      router.push('/instructor/dashboard');
    }
  }, [userData, userError, isLoadingUser, router]);

  /**
   * Handle user logout
   */
  const handleLogout = () => {
    logger.info('Student logging out');
    logout();
  };

  // Helpers
  const formatPhoneReadable = (phone?: string | null) => {
    if (!phone) return '—';
    // Expect E.164 or +1XXXXXXXXXX
    const digits = phone.replace(/\D/g, '');
    if (digits.length >= 11) {
      const d = digits.slice(-10);
      return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
    }
    if (digits.length === 10) {
      return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    }
    return phone;
  };

  const inferCityStateFromZip = (zip?: string) => {
    if (!zip) return null;
    const prefix = zip.slice(0, 3);
    // NYC-focused inference (coarse). Extend as needed.
    const map: Record<string, { city: string; state: string }> = {
      '100': { city: 'New York', state: 'NY' },
      '101': { city: 'New York', state: 'NY' },
      '102': { city: 'New York', state: 'NY' },
      '103': { city: 'Staten Island', state: 'NY' },
      '104': { city: 'Bronx', state: 'NY' },
      '111': { city: 'Long Island City', state: 'NY' },
      '112': { city: 'Brooklyn', state: 'NY' },
      '113': { city: 'Queens', state: 'NY' },
      '114': { city: 'Queens', state: 'NY' },
      '116': { city: 'Queens', state: 'NY' },
    };
    return map[prefix] || null;
  };

  const decodeUlidTimestamp = (ulid: string): Date | null => {
    // ULID: first 10 chars are Crockford base32 timestamp (ms)
    const ALPH = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
    if (!ulid || ulid.length < 10) return null;
    let ts = 0;
    for (let i = 0; i < 10; i++) {
      const char = ulid.charAt(i);
      if (!char) return null;
      const v = ALPH.indexOf(char);
      if (v === -1) return null;
      ts = ts * 32 + v;
    }
    return new Date(ts);
  };

  const memberSince = decodeUlidTimestamp(userData?.id || '');

  // Note: Profile photo uploads are handled by <ProfilePictureUpload />

  // Load addresses
  const loadAddresses = async () => {
    try {
      setIsLoadingAddresses(true);
      const res = await fetchWithAuth('/api/addresses/me');
      if (!res.ok) {
        setAddresses([]);
        return;
      }
      const data = await res.json();
      setAddresses(data.items || []);
    } catch {
      setAddresses([]);
    } finally {
      setIsLoadingAddresses(false);
    }
  };

  useEffect(() => {
    void loadAddresses();
    // Preload TFA status in background
    void (async () => {
      try {
        const res = await fetchWithAuth('/api/auth/2fa/status');
        if (res.ok) {
          const data = await res.json();
          setTfaStatus({ enabled: !!data.enabled, verified_at: data.verified_at || null, last_used_at: data.last_used_at || null });
        }
      } catch {}
    })();
  }, []);

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#7E22CE]"></div>
      </div>
    );
  }

  if (!userData) return null;

  return (
    <div className="min-h-screen bg-gray-50 relative">
      {/* Background Image */}
      <div
        className="fixed inset-0 z-0"
        style={{
          backgroundImage: `url('${getActivityBackground('home', 'desktop')}')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          opacity: 0.3,
        }}
        aria-hidden="true"
      />

      {/* Content wrapper */}
      <div className="relative z-10">
      {/* Navigation - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">
              iNSTAiNSTRU
            </h1>
          </Link>
          <div className="flex items-center gap-4 pr-4">
            <Link
              href="/student/lessons"
              className="text-gray-700 hover:text-[#7E22CE] font-medium"
            >
              My Lessons
            </Link>
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      {/* Stats bar (dismissible) - matching home page notification style */}
      {isStatsVisible && (
        <div className="bg-gray-50 dark:bg-gray-900/20 animate-slide-down">
          <div className="w-full">
            <div className="flex items-center justify-between py-2 px-8">
              <div className="flex items-center pl-4">
                <p className="text-sm font-bold text-gray-600 dark:text-gray-400">
                  You&apos;ve completed 12 lessons this year. 3 more to reach Bronze status!
                </p>
              </div>
              <button
                onClick={() => setIsStatsVisible(false)}
                className="p-1 rounded-full hover:bg-gray-200 dark:hover:bg-gray-800/30 transition-colors mr-4"
                aria-label="Dismiss notification"
              >
                <X className="h-4 w-4 text-gray-600 dark:text-gray-400" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-12 gap-6">
          {/* Sidebar tabs */}
          <aside className="col-span-12 md:col-span-3">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              {tabs.map(({ key, label, icon: Icon }) => {
                const isActive = activeTab === key;
                return (
                  <button
                    key={key}
                    onClick={() => {
                      setActiveTab(key);
                      const params = new URLSearchParams(Array.from(searchParams.entries()));
                      params.set('tab', key);
                      router.replace(`${pathname}?${params.toString()}`);
                    }}
                    className={
                      `w-full flex items-center gap-3 rounded-lg px-4 py-3 text-base font-semibold mb-2 transition-all cursor-pointer ` +
                      (isActive
                        ? 'bg-purple-50 text-gray-600 border border-purple-200'
                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-700')
                    }
                  >
                    <Icon className="h-5 w-5" />
                    <span>{label}</span>
                  </button>
                );
              })}
            </div>
          </aside>

        {/* Main content */}
          <section className="col-span-12 md:col-span-9">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 sm:p-8">
              {activeTab === 'profile' && (
                <div className="space-y-8">

                  {/* Account Information */}
                  <div>
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-semibold text-gray-900">Account Information</h3>
                      <button
                        className="text-sm font-medium text-[#7E22CE] hover:text-[#7E22CE] cursor-pointer"
                        onClick={() => {
                          logger.debug('Edit profile clicked');
                          setShowEditProfile(true);
                        }}
                      >
                        Edit
                      </button>
                    </div>
                    <div className="flex items-start gap-5">
                      <div className="relative group">
                        {(() => {
                          const u = userData as unknown as { has_profile_picture?: boolean };
                          return Boolean(u?.has_profile_picture);
                        })() ? (
                          <ProfilePictureUpload
                            size={144}
                            ariaLabel="Change profile picture"
                            onCompleted={() => { setProfilePhoto(null); void refetchUserData(); }}
                            trigger={
                              <UserAvatar
                                user={{
                                  id: userData.id,
                                  first_name: userData.first_name,
                                  last_name: userData.last_name,
                                  email: userData.email,
                                  has_profile_picture: Boolean((userData as unknown as { has_profile_picture?: boolean })?.has_profile_picture),
                                  ...((userData as unknown as { profile_picture_version?: number })?.profile_picture_version && {
                                    profile_picture_version: (userData as unknown as { profile_picture_version?: number }).profile_picture_version
                                  }),
                                }}
                                size={144}
                                className="cursor-pointer"
                              />
                            }
                          />
                        ) : (
                          <ProfilePictureUpload size={144} onCompleted={() => { setProfilePhoto(null); void refetchUserData(); }} />
                        )}
                      </div>
                      <div className="space-y-1.5 text-sm text-gray-700">
                        <p className="text-2xl font-bold text-[#7E22CE]">{userData?.first_name} {userData?.last_name}</p>
                        <p>{userData?.email}</p>
                        <p>{formatPhoneReadable(userData?.phone)}</p>
                        <p>
                          {(() => {
                            const z = userData?.zip_code;
                            const info = inferCityStateFromZip(z);
                            return info ? `${info.city}, ${info.state}, ${z}` : z || '—';
                          })()}
                        </p>
                        <p className="text-[#7E22CE]/90">
                          Member since: {memberSince ? memberSince.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : '—'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Achievements & Badges */}
                  <div className="border-b border-gray-200 mb-6"></div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <h3 className="text-lg font-semibold text-gray-900">Achievements & Badges</h3>
                      <button
                        onClick={() => setShowAchievementsModal(true)}
                        className="text-sm font-medium text-[#7E22CE] hover:text-[#7E22CE] cursor-pointer"
                      >
                        Explore
                      </button>
                    </div>
                    <p className="text-sm text-gray-600 mb-4">Earn badges as you learn and teach!</p>
                    <div className="flex gap-6">
                      {/* Badge 1: 5 Lessons */}
                      <div className="group relative flex flex-col items-center cursor-pointer">
                        <Award
                          size={32}
                          strokeWidth={1.5}
                          className="mb-2 text-yellow-500 transition-colors"
                        />
                        <p className="text-sm font-medium text-gray-700 whitespace-nowrap">5 Lessons</p>

                        {/* Tooltip */}
                        <div className="absolute -top-12 left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                          <div className="bg-white text-[#7E22CE] text-xs rounded-lg py-2 px-3 whitespace-nowrap border border-purple-200 shadow-lg">
                            5 Lessons – Completed your first 5 lessons!
                            <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
                              <div className="w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-white"></div>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Badge 2: Quick Learner */}
                      <div className="group relative flex flex-col items-center cursor-pointer">
                        <Zap
                          size={32}
                          strokeWidth={1.5}
                          className="mb-2 text-yellow-500 transition-colors"
                        />
                        <p className="text-sm font-medium text-gray-700 whitespace-nowrap">Quick Learner</p>

                        {/* Tooltip */}
                        <div className="absolute -top-12 left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                          <div className="bg-white text-[#7E22CE] text-xs rounded-lg py-2 px-3 whitespace-nowrap border border-purple-200 shadow-lg">
                            Quick Learner – Finished 3 lessons in the first week.
                            <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
                              <div className="w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-white"></div>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Badge 3: Top Student */}
                      <div className="group relative flex flex-col items-center cursor-pointer">
                        <Star
                          size={32}
                          strokeWidth={1.5}
                          className="mb-2 text-yellow-500 transition-colors"
                        />
                        <p className="text-sm font-medium text-gray-700 whitespace-nowrap">Top Student</p>

                        {/* Tooltip */}
                        <div className="absolute -top-12 left-1/2 transform -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                          <div className="bg-white text-[#7E22CE] text-xs rounded-lg py-2 px-3 whitespace-nowrap border border-purple-200 shadow-lg">
                            Top Student – Rated 5 stars by 3 instructors.
                            <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-px">
                              <div className="w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-white"></div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Addresses */}
                  <div className="border-b border-gray-200 mb-6"></div>
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-lg font-semibold text-gray-900">Addresses</h3>
                      <button
                        className="text-sm font-medium text-[#7E22CE] hover:text-[#7E22CE] cursor-pointer"
                        onClick={() => setShowAddressModal({ mode: 'create' })}
                      >
                        + Add
                      </button>
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      {isLoadingAddresses && (
                        <div className="rounded-xl border border-gray-200 p-4 text-sm text-gray-600">Loading addresses…</div>
                      )}
                      {!isLoadingAddresses && (addresses?.length || 0) === 0 && (
                        <div className="rounded-xl border border-gray-200 p-4 text-sm text-gray-600">No addresses added yet.</div>
                      )}
                      {!isLoadingAddresses && (addresses || []).map((a) => (
                        <div key={a.id} className="rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow">
                          <p className="font-medium text-gray-900">
                            {(a.label ? a.label.charAt(0).toUpperCase() + a.label.slice(1) : 'Address')} {a.is_default ? '(Default)' : ''}
                          </p>
                          <p className="text-sm text-gray-600">
                            {[a.street_1, a.street_2].filter(Boolean).join(', ')}{[a.city, a.state].some(Boolean) ? `, ${[a.city, a.state].filter(Boolean).join(', ')}` : ''}{a.zip_code ? `, ${a.zip_code}` : ''}
                          </p>
                          <div className="mt-2 flex gap-3 text-sm">
                            <button
                              className="text-[#7E22CE] hover:text-[#7E22CE]"
                              onClick={() => setShowAddressModal({ mode: 'edit', address: a })}
                            >
                              Edit
                            </button>
                            <button
                              className="text-gray-500 hover:text-gray-700"
                              onClick={async () => {
                                // Custom confirm modal
                                const ok = await new Promise<boolean>((resolve) => {
                                  const overlay = document.createElement('div');
                                  overlay.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4';
                                  const modal = document.createElement('div');
                                  modal.className = 'w-full max-w-sm rounded-lg bg-white p-6 shadow-lg ring-1 ring-gray-200';
                                  modal.innerHTML = `
                                    <h3 class="text-base font-semibold text-gray-900">Remove address</h3>
                                    <p class="mt-2 text-sm text-gray-600">Are you sure you want to remove this saved address?</p>
                                    <div class="mt-5 flex justify-end gap-3">
                                      <button id="cancelBtn" class="rounded-md border border-gray-200 px-4 py-2 text-sm">Cancel</button>
                                      <button id="confirmBtn" class="rounded-md bg-[#7E22CE] px-4 py-2 text-sm text-white hover:bg-[#7E22CE]">Remove</button>
                                    </div>
                                  `;
                                  overlay.appendChild(modal);
                                  document.body.appendChild(overlay);
                                  const cleanup = () => { try { document.body.removeChild(overlay); } catch {} };
                                  modal.querySelector('#cancelBtn')?.addEventListener('click', () => { cleanup(); resolve(false); });
                                  modal.querySelector('#confirmBtn')?.addEventListener('click', () => { cleanup(); resolve(true); });
                                });
                                if (!ok) return;
                                const res = await fetchWithAuth(`/api/addresses/me/${a.id}`, { method: 'DELETE' });
                                if (res.ok) {
                                  toast.success('Address removed', {
                                    style: {
                                      background: '#6b21a8',
                                      color: 'white',
                                      border: 'none',
                                      boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
                                    },
                                  });
                                  void loadAddresses();
                                } else {
                                  toast.error('Failed to remove address', {
                                    style: {
                                      background: '#fbbf24',
                                      color: '#000000',
                                      border: 'none',
                                    },
                                  });
                                }
                              }}
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Security */}
                  <div className="border-b border-gray-200 mb-6"></div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Security</h3>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="rounded-lg bg-gray-100 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-200 hover:text-gray-900 transition-all cursor-pointer"
                        onClick={() => setShowChangePassword(true)}
                      >
                        Change Password
                      </button>
                      <button
                        className="rounded-lg bg-gray-100 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-200 hover:text-gray-900 transition-all cursor-pointer"
                        onClick={() => setShowTfaModal(true)}
                      >
                        {tfaStatus?.enabled ? 'Manage Two-Factor Authentication' : 'Enable Two-Factor Authentication'}
                      </button>
                    </div>
                    {tfaStatus && (
                      <p className="mt-2 text-sm text-gray-600">
                        2FA Status: {tfaStatus.enabled ? 'Enabled' : 'Disabled'}{tfaStatus.last_used_at ? ` • Last used: ${new Date(tfaStatus.last_used_at).toLocaleString()}` : ''}
                      </p>
                    )}
                  </div>

                  <p className="mt-6 text-sm text-gray-600">
                    Manage your link, invites, and rewards in the Rewards tab.
                  </p>

                  {/* Account Management (placeholder) */}
                  <div className="border-b border-gray-200 mb-6"></div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Account Management</h3>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="py-2.5 px-4 rounded-lg text-sm font-medium bg-white border border-[#7E22CE] text-[#7E22CE] hover:bg-purple-50 transition-colors cursor-pointer"
                        onClick={() => setShowDelete(true)}
                      >
                        Delete Account
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'billing' && (
                <BillingTab userId={userData?.id || ''} />
              )}
              {activeTab === 'notifications' && (
                <NotificationsTab />
              )}

              {activeTab === 'favorites' && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">Quickly access your favorite subjects and instructors</p>

                  {isLoadingFavorites && (
                    <div className="rounded-xl border border-gray-200 p-4 text-sm text-gray-600">Loading favorites…</div>
                  )}

                  {!isLoadingFavorites && favoritesError && (
                    <div className="rounded-xl border border-gray-200 p-4 text-sm text-red-600">Failed to load favorites.</div>
                  )}

                  {!isLoadingFavorites && !favoritesError && (favoritesData?.favorites?.length || 0) === 0 && (
                    <div className="rounded-xl border border-gray-200 p-6 text-sm text-gray-700 flex items-center justify-between">
                      <div>No favorite instructors yet.</div>
                      <Link href="/" className="rounded-lg bg-[#7E22CE] px-4 py-2.5 text-white text-sm font-medium hover:bg-[#7E22CE] transition-all">Find More Instructors</Link>
                    </div>
                  )}

                  {!isLoadingFavorites && !favoritesError && (favoritesData?.favorites?.length || 0) > 0 && (
                    <div className="grid grid-cols-1 gap-4">
                      {favoritesData!.favorites.map((fav) => {
                        const name = fav.profile?.user
                          ? `${fav.profile.user.first_name} ${fav.profile.user.last_initial ? fav.profile.user.last_initial + '.' : ''}`
                          : `${fav.first_name}${fav.last_name ? ' ' + fav.last_name.charAt(0) + '.' : ''}`;
                        const services = fav.profile?.services || [];
                        const uniqueServices = Array.from(
                          new Set(
                            services
                              .map((s) => {
                                const withNames = s as Partial<{ skill: string; name: string }>;
                                const label = withNames.skill ?? withNames.name ?? '';
                                return String(label).split(' - ')[0];
                              })
                              .filter((v): v is string => Boolean(v))
                          )
                        );
                        const primaryRate = services?.[0]?.hourly_rate as number | undefined;
                        const primarySubject = uniqueServices[0] || null;
                        const primaryArea = getServiceAreaDisplay(fav.profile ?? {}) || null;
                        const yearsExp = fav.profile?.years_experience || null;

                        return (
                          <div
                            key={fav.id}
                            className="relative rounded-xl border border-gray-200 p-4 pr-10 hover:shadow-sm hover:bg-gray-50 transition-all cursor-pointer"
                            onClick={() => router.push(`/instructors/${fav.id}`)}
                          >
                            <div className="flex items-start gap-4">
                              <UserAvatar
                                user={{
                                  id: fav.id,
                                  ...((fav.first_name || fav.profile?.user?.first_name) && {
                                    first_name: fav.first_name || fav.profile?.user?.first_name || ''
                                  }),
                                  ...(fav.last_name && { last_name: fav.last_name }),
                                  ...(fav.email && { email: fav.email }),
                                  // Keep avatar glyph fallback; do not pass non-existent fields from minimal API
                                }}
                                size={48}
                                className="h-12 w-12"
                              />
                              <div>
                                <p className="font-semibold text-gray-900">{name}</p>
                                {(primarySubject || yearsExp) && (
                                  <p className="mt-1 text-xs text-gray-700">
                                    {primarySubject ? <span>{primarySubject}</span> : null}
                                    {primarySubject && yearsExp ? <span> · </span> : null}
                                    {yearsExp ? <span>{yearsExp} yrs experience</span> : null}
                                  </p>
                                )}
                                {(primaryArea || typeof primaryRate === 'number') && (
                                  <p className="mt-1 text-xs text-gray-600">
                                    {primaryArea ? <span>{primaryArea}</span> : null}
                                    {primaryArea && typeof primaryRate === 'number' ? <span> · </span> : null}
                                    {typeof primaryRate === 'number' ? <span>${'{'}primaryRate{'}'}/hour</span> : null}
                                  </p>
                                )}
                              </div>
                            </div>
                            <button
                              className="absolute top-2 right-2 p-1 text-gray-500 hover:text-gray-700 cursor-pointer"
                              aria-label="Remove favorite"
                              title="Remove"
                              onClick={async (e) => {
                                e.stopPropagation();
                                try {
                                  await favoritesApi.remove(fav.id);
                                  toast.success('Removed from favorites', {
                                    style: {
                                      background: '#6b21a8',
                                      color: 'white',
                                      border: 'none',
                                      boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
                                    },
                                  });
                                  await refetchFavorites();
                                } catch {
                                  toast.error('Failed to update favorite', {
                                    style: {
                                      background: '#fbbf24',
                                      color: '#000000',
                                      border: 'none',
                                    },
                                  });
                                }
                              }}
                            >
                              <X className="h-4 w-4" aria-hidden="true" />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'rewards' && (
                <RewardsPanel {...(userData?.first_name ? { inviterName: userData.first_name } : {})} />
              )}

              {activeTab !== 'profile' && activeTab !== 'favorites' && activeTab !== 'billing' && activeTab !== 'notifications' && activeTab !== 'rewards' && (
                <div className="text-sm text-gray-600">
                  <p>Settings for <span className="font-medium">{tabs.find(t => t.key === activeTab)?.label}</span> will appear here.</p>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
      {/* Modals */}
      {showDelete && (
        <DeleteAccountModal
          email={userData?.email}
          onClose={() => setShowDelete(false)}
          onDeleted={() => {
            setShowDelete(false);
            handleLogout();
            router.replace('/');
          }}
        />
      )}

      {showChangePassword && (
        <ChangePasswordModal
          onClose={() => setShowChangePassword(false)}
        />
      )}

      {showAddressModal && (
        <AddressModal
          mode={showAddressModal.mode}
          {...(showAddressModal.mode === 'edit' && showAddressModal.address && { address: showAddressModal.address })}
          onClose={() => setShowAddressModal(null)}
          onSaved={() => {
            setShowAddressModal(null);
            void loadAddresses();
          }}
        />
      )}

      {showTfaModal && (
        <TfaModal
          onClose={() => setShowTfaModal(false)}
          onChanged={async () => {
            try {
              const res = await fetchWithAuth('/api/auth/2fa/status');
              if (res.ok) {
                const data = await res.json();
                setTfaStatus({ enabled: !!data.enabled, verified_at: data.verified_at || null, last_used_at: data.last_used_at || null });
              }
            } catch {}
          }}
        />
      )}

      {/* Edit Profile Modal */}
      {showEditProfile && userData && (
        <EditProfileModal
          user={userData as unknown as Record<string, unknown>}
          onClose={() => setShowEditProfile(false)}
          onSaved={() => {
            setShowEditProfile(false);
            void refetchUserData(); // Refresh user data without page reload
          }}
        />
      )}

      {/* Achievements Modal */}
      {showAchievementsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setShowAchievementsModal(false)}
          />
          <div className="relative w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-lg bg-white shadow-lg">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold text-gray-900">Explore Achievements</h2>
                <button
                  onClick={() => setShowAchievementsModal(false)}
                  className="p-1 hover:bg-gray-100 rounded-full transition-colors"
                  aria-label="Close achievements modal"
                >
                  <X className="h-5 w-5 text-gray-500" aria-hidden="true" />
                </button>
              </div>
              <p className="mt-1 text-sm text-gray-600">
                Here are all the badges you can earn. You&apos;ve unlocked 3 so far — keep going!
              </p>
            </div>

            <div className="p-6 space-y-8">
              {/* Earned Badges */}
              <div>
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle className="h-5 w-5 text-yellow-500" />
                  <h3 className="text-lg font-semibold text-gray-900">Earned</h3>
                </div>

                <div className="space-y-4">
                  {/* 5 Lessons Badge */}
                  <div className="flex items-start gap-4 p-4 rounded-lg bg-purple-50 border border-purple-200">
                    <div className="shrink-0">
                      <Award size={32} strokeWidth={1.5} className="text-yellow-500" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900">5 Lessons</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        You earned this by completing 5 lessons.
                      </p>
                    </div>
                  </div>

                  {/* Quick Learner Badge */}
                  <div className="flex items-start gap-4 p-4 rounded-lg bg-purple-50 border border-purple-200">
                    <div className="shrink-0">
                      <Zap size={32} strokeWidth={1.5} className="text-yellow-500" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900">Quick Learner</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        Awarded for finishing 3 lessons in your first week.
                      </p>
                    </div>
                  </div>

                  {/* Top Student Badge */}
                  <div className="flex items-start gap-4 p-4 rounded-lg bg-purple-50 border border-purple-200">
                    <div className="shrink-0">
                      <Star size={32} strokeWidth={1.5} className="text-yellow-500" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-900">Top Student</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        Earned by receiving 3 five-star reviews.
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Locked Badges */}
              <div>
                <div className="flex items-center gap-2 mb-4">
                  <Lock className="h-5 w-5 text-gray-500" />
                  <h3 className="text-lg font-semibold text-gray-900">Locked (How to Unlock)</h3>
                </div>

                <div className="space-y-4">
                  {/* 10 Lessons Badge */}
                  <div className="flex items-start gap-4 p-4 rounded-lg bg-gray-50 border border-gray-200 opacity-75">
                    <div className="shrink-0 relative">
                      <BookOpen size={32} strokeWidth={1.5} className="text-gray-400" />
                      <Lock className="h-3 w-3 text-gray-600 absolute -bottom-1 -right-1" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-700">10 Lessons</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        Complete 10 lessons to unlock.
                      </p>
                    </div>
                  </div>

                  {/* Consistent Learner Badge */}
                  <div className="flex items-start gap-4 p-4 rounded-lg bg-gray-50 border border-gray-200 opacity-75">
                    <div className="shrink-0 relative">
                      <Calendar size={32} strokeWidth={1.5} className="text-gray-400" />
                      <Lock className="h-3 w-3 text-gray-600 absolute -bottom-1 -right-1" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-700">Consistent Learner</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        Book lessons 3 weeks in a row to unlock.
                      </p>
                    </div>
                  </div>

                  {/* Anniversary Badge */}
                  <div className="flex items-start gap-4 p-4 rounded-lg bg-gray-50 border border-gray-200 opacity-75">
                    <div className="shrink-0 relative">
                      <Target size={32} strokeWidth={1.5} className="text-gray-400" />
                      <Lock className="h-3 w-3 text-gray-600 absolute -bottom-1 -right-1" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-700">Anniversary Badge</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        Stay active for 1 year to unlock.
                      </p>
                    </div>
                  </div>

                  {/* Explorer Badge */}
                  <div className="flex items-start gap-4 p-4 rounded-lg bg-gray-50 border border-gray-200 opacity-75">
                    <div className="shrink-0 relative">
                      <Globe size={32} strokeWidth={1.5} className="text-gray-400" />
                      <Lock className="h-3 w-3 text-gray-600 absolute -bottom-1 -right-1" />
                    </div>
                    <div>
                      <h4 className="font-semibold text-gray-700">Explorer</h4>
                      <p className="text-sm text-gray-600 mt-1">
                        Take lessons in 3 different subjects to unlock.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

function NotificationsTab() {
  const [preferences, setPreferences] = useState({
    lessonUpdates: { email: true, sms: true, push: false },
    instructorMessages: { email: true, sms: true, push: true },
    learningTips: { email: true, sms: false, push: true },
    systemUpdates: { email: true, sms: false, push: false },
    promotionalOffers: { email: false, sms: false, push: false },
  });

  const [reminderTiming, setReminderTiming] = useState('1440'); // 24 hours in minutes
  const [quietHoursStart, setQuietHoursStart] = useState('22:00');
  const [quietHoursEnd, setQuietHoursEnd] = useState('08:00');
  const [saving, setSaving] = useState(false);
  const [usingRecommended, setUsingRecommended] = useState(false);

  const handleToggle = (category: string, channel: 'email' | 'sms' | 'push') => {
    setPreferences(prev => ({
      ...prev,
      [category]: {
        ...prev[category as keyof typeof prev],
        [channel]: !prev[category as keyof typeof prev][channel]
      }
    }));
    setUsingRecommended(false); // User manually changed settings
  };

  const applyRecommendedSettings = () => {
    if (usingRecommended) {
      // Toggle off - just change the state, keep current settings
      setUsingRecommended(false);
    } else {
      // Toggle on - apply recommended settings
      setPreferences({
        lessonUpdates: { email: true, sms: true, push: false },
        instructorMessages: { email: true, sms: true, push: true },
        learningTips: { email: true, sms: false, push: true },
        systemUpdates: { email: true, sms: false, push: false },
        promotionalOffers: { email: false, sms: false, push: false },
      });
      setReminderTiming('1440'); // 24 hours
      setQuietHoursStart('22:00');
      setQuietHoursEnd('08:00');
      setUsingRecommended(true);
      toast.success('Recommended settings applied', {
        style: {
          background: '#6b21a8',
          color: 'white',
        },
      });
    }
  };

  const isQuietHoursOff = quietHoursStart === quietHoursEnd;

  const handleSave = async () => {
    setSaving(true);
    // TODO: Implement API call to save preferences
    await new Promise(resolve => setTimeout(resolve, 1000));
    toast.success('Notification preferences saved', {
      style: {
        background: '#6b21a8',
        color: 'white',
      },
    });
    setSaving(false);
  };

  // Toggle Switch Component
  const ToggleSwitch = ({ checked, onChange }: { checked: boolean; onChange: () => void }) => (
    <button
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        checked ? 'bg-purple-600' : 'bg-gray-300'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );

  // Custom Time Picker Component
  const CustomTimePicker = ({ value, onChange }: { value: string; onChange: (value: string) => void }) => {
    const [isOpen, setIsOpen] = useState(false);
    const parts = value.split(':');
    const hour = at(parts, 0) || '0';
    const minute = at(parts, 1) || '0';
    const hourNum = parseInt(hour) || 0;
    const displayHour = hourNum === 0 ? 12 : hourNum > 12 ? hourNum - 12 : hourNum;
    const period = hourNum >= 12 ? 'PM' : 'AM';

    const hours = Array.from({ length: 12 }, (_, i) => i + 1);
    const minutes = Array.from({ length: 60 }, (_, i) => i.toString().padStart(2, '0'));

    const handleTimeChange = (newHour: number, newMinute: string, newPeriod: string) => {
      let h = newHour;
      if (newPeriod === 'PM' && h !== 12) h += 12;
      if (newPeriod === 'AM' && h === 12) h = 0;
      const formattedTime = `${h.toString().padStart(2, '0')}:${newMinute}`;
      onChange(formattedTime);
      setIsOpen(false);
    };

    return (
      <div className="relative">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/25 focus:border-purple-500 min-w-[120px] text-left"
        >
          {displayHour}:{minute} {period}
        </button>

        {isOpen && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setIsOpen(false)}
            />
            <div className="absolute top-full mt-1 z-20 bg-white rounded-lg shadow-lg border border-gray-200 p-3 min-w-[200px]">
              <div className="flex gap-2">
                {/* Hour selector */}
                <div className="flex-1">
                  <div className="text-xs font-medium text-gray-600 mb-1">Hour</div>
                  <div className="h-20 overflow-y-auto border border-gray-200 rounded scrollbar-hide">
                    {hours.map(h => (
                      <button
                        key={h}
                        onClick={() => handleTimeChange(h, minute, period)}
                        className={`w-full px-2 py-1 text-sm hover:bg-purple-50 ${
                          displayHour === h ? 'bg-purple-100 text-[#7E22CE] font-medium' : ''
                        }`}
                      >
                        {h}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Minute selector */}
                <div className="flex-1">
                  <div className="text-xs font-medium text-gray-600 mb-1">Minute</div>
                  <div className="h-20 overflow-y-auto border border-gray-200 rounded scrollbar-hide">
                    {minutes.filter((_, i) => i % 5 === 0).map(m => (
                      <button
                        key={m}
                        onClick={() => handleTimeChange(displayHour, m, period)}
                        className={`w-full px-2 py-1 text-sm hover:bg-purple-50 ${
                          minute === m ? 'bg-purple-100 text-[#7E22CE] font-medium' : ''
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>

                {/* AM/PM selector */}
                <div className="flex-1">
                  <div className="text-xs font-medium text-gray-600 mb-1">Period</div>
                  <div className="border border-gray-200 rounded">
                    <button
                      onClick={() => handleTimeChange(displayHour, minute, 'AM')}
                      className={`w-full px-2 py-2 text-sm hover:bg-purple-50 ${
                        period === 'AM' ? 'bg-purple-100 text-[#7E22CE] font-medium' : ''
                      }`}
                    >
                      AM
                    </button>
                    <button
                      onClick={() => handleTimeChange(displayHour, minute, 'PM')}
                      className={`w-full px-2 py-2 text-sm hover:bg-purple-50 border-t border-gray-200 ${
                        period === 'PM' ? 'bg-purple-100 text-[#7E22CE] font-medium' : ''
                      }`}
                    >
                      PM
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Use Recommended Settings */}
      <div className="flex items-center justify-between p-4 rounded-lg bg-gray-50 border border-gray-200">
        <div>
          <span className="text-sm font-medium text-gray-900">Use Recommended Settings</span>
          <p className="text-xs text-gray-500 mt-0.5">Apply optimal notification preferences for most users</p>
        </div>
        <ToggleSwitch
          checked={usingRecommended}
          onChange={applyRecommendedSettings}
        />
      </div>

      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Notification Preferences</h3>

        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4 pb-3 border-b border-gray-200">
            <div className="text-sm font-medium text-gray-700">Notification Type</div>
            <div className="text-sm font-medium text-gray-700 text-center">Email</div>
            <div className="text-sm font-medium text-gray-700 text-center">SMS</div>
            <div className="text-sm font-medium text-gray-700 text-center">Push</div>
          </div>

          {/* Lesson Updates - Most Important */}
          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Lesson Updates</div>
              <div className="text-xs text-gray-500">Booking confirmations, reminders, cancellations</div>
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.lessonUpdates.email}
                onChange={() => handleToggle('lessonUpdates', 'email')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.lessonUpdates.sms}
                onChange={() => handleToggle('lessonUpdates', 'sms')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.lessonUpdates.push}
                onChange={() => handleToggle('lessonUpdates', 'push')}
              />
            </div>
          </div>

          {/* Instructor Messages - Second Most Important */}
          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Instructor Messages</div>
              <div className="text-xs text-gray-500">Direct messages, replies, updates from instructors</div>
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.instructorMessages.email}
                onChange={() => handleToggle('instructorMessages', 'email')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.instructorMessages.sms}
                onChange={() => handleToggle('instructorMessages', 'sms')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.instructorMessages.push}
                onChange={() => handleToggle('instructorMessages', 'push')}
              />
            </div>
          </div>

          {/* Learning Tips */}
          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Learning Tips & Achievements</div>
              <div className="text-xs text-gray-500">Weekly tips, progress updates, milestones</div>
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.learningTips.email}
                onChange={() => handleToggle('learningTips', 'email')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.learningTips.sms}
                onChange={() => handleToggle('learningTips', 'sms')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.learningTips.push}
                onChange={() => handleToggle('learningTips', 'push')}
              />
            </div>
          </div>

          {/* System & Policy Updates */}
          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">System & Policy Updates</div>
              <div className="text-xs text-gray-500">Important platform changes, maintenance, terms updates</div>
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.systemUpdates.email}
                onChange={() => handleToggle('systemUpdates', 'email')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.systemUpdates.sms}
                onChange={() => handleToggle('systemUpdates', 'sms')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.systemUpdates.push}
                onChange={() => handleToggle('systemUpdates', 'push')}
              />
            </div>
          </div>

          {/* Promotional Offers - Least Important */}
          <div className="grid grid-cols-4 gap-4 items-start py-2">
            <div>
              <div className="font-medium text-gray-900">Promotional Offers</div>
              <div className="text-xs text-gray-500">Discounts, special offers, new features</div>
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.promotionalOffers.email}
                onChange={() => handleToggle('promotionalOffers', 'email')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.promotionalOffers.sms}
                onChange={() => handleToggle('promotionalOffers', 'sms')}
              />
            </div>
            <div className="flex justify-center">
              <ToggleSwitch
                checked={preferences.promotionalOffers.push}
                onChange={() => handleToggle('promotionalOffers', 'push')}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-gray-200 pt-6">
        <h4 className="font-medium text-gray-900 mb-4">Lesson Reminder Timing</h4>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-700">Send reminders</span>
          <div className="relative">
            <select
              value={reminderTiming}
              onChange={(e) => setReminderTiming(e.target.value)}
              className="appearance-none rounded-lg border border-purple-200 bg-white px-3 py-2 pr-10 text-sm text-gray-900 shadow-sm hover:border-purple-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#7E22CE] focus:border-purple-500 transition-all cursor-pointer"
              style={{
                backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%239333ea' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                backgroundPosition: 'right 0.5rem center',
                backgroundRepeat: 'no-repeat',
                backgroundSize: '1.5em 1.5em',
                paddingRight: '2.5rem',
                backgroundColor: 'white',
              }}
            >
              <option value="0" style={{ backgroundColor: 'white' }}>None - Don&apos;t send reminders</option>
              <option value="60" style={{ backgroundColor: 'white' }}>1 hour before lesson</option>
              <option value="360" style={{ backgroundColor: 'white' }}>6 hours before lesson</option>
              <option value="1440" style={{ backgroundColor: 'white' }}>24 hours before lesson</option>
              <option value="2880" style={{ backgroundColor: 'white' }}>2 days before lesson</option>
            </select>
          </div>
          <span className="text-sm text-gray-700">lesson starts</span>
        </div>
        <p className="text-xs text-gray-500 mt-2">You&apos;ll receive a reminder at your selected time before each scheduled lesson.</p>
      </div>

      <div className="border-t border-gray-200 pt-6">
        <h4 className="font-medium text-gray-900 mb-4">Quiet Hours</h4>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-700">Mute notifications between</span>
            <CustomTimePicker
              value={quietHoursStart}
              onChange={setQuietHoursStart}
            />
            <span className="text-sm text-gray-700">and</span>
            <CustomTimePicker
              value={quietHoursEnd}
              onChange={setQuietHoursEnd}
            />
          </div>
          {isQuietHoursOff && (
            <p className="text-xs text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
              💡 Tip: Set the same time for both fields to turn off quiet hours completely.
            </p>
          )}
          {!isQuietHoursOff && (
            <p className="text-xs text-gray-500">
              Notifications will be silenced during these hours. Urgent lesson updates may still come through.
            </p>
          )}
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
        <button
          className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          onClick={() => window.location.reload()}
        >
          Cancel
        </button>
        <button
          className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors ${
            saving
              ? 'bg-purple-400 cursor-not-allowed'
              : 'bg-[#7E22CE] hover:bg-[#7E22CE]'
          }`}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
}

function TfaModal({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const [step, setStep] = useState<'idle' | 'show' | 'verify' | 'enabled' | 'disabled'>('idle');
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Load current status; if disabled, immediately initiate and show QR (no confirmation step)
    (async () => {
      try {
        const res = await fetchWithAuth('/api/auth/2fa/status');
        if (res.ok) {
          const data = await res.json();
          if (data.enabled) {
            setStep('enabled');
          } else {
            setStep('show');
            await initiate();
          }
        }
      } catch {}
    })();
  }, []);

  const initiate = async () => {
    setError(null); setLoading(true);
    try {
      const res = await fetchWithAuth('/api/auth/2fa/setup/initiate', { method: 'POST' });
      if (!res.ok) {
        setError('Failed to initiate 2FA.'); setLoading(false); return;
      }
      const data = await res.json();
      setQr(data.qr_code_data_url);
      setSecret(data.secret);
      setStep('show');
    } catch { setError('Network error.'); } finally { setLoading(false); }
  };

  const verify = async () => {
    setError(null); setLoading(true);
    try {
      const res = await fetchWithAuth('/api/auth/2fa/setup/verify', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code })
      });
      if (!res.ok) { const b = await res.json().catch(() => ({})); setError(b.detail || 'That code didn\'t work. Please try again.'); setLoading(false); return; }
      const data = await res.json();
      setBackupCodes(data.backup_codes || []);
      setStep('enabled');
      onChanged();
    } catch { setError('Network error.'); } finally { setLoading(false); }
  };

  const disable = async () => {
    setError(null); setLoading(true);
    try {
      const res = await fetchWithAuth('/api/auth/2fa/disable', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: currentPassword })
      });
      if (!res.ok) { const b = await res.json().catch(() => ({})); setError(b.detail || 'Failed to disable'); setLoading(false); return; }
      setStep('disabled');
      onChanged();
    } catch { setError('Network error.'); } finally { setLoading(false); }
  };

  const regen = async () => {
    setError(null); setLoading(true);
    try {
      const res = await fetchWithAuth('/api/auth/2fa/regenerate-backup-codes', { method: 'POST' });
      if (!res.ok) { setError('Failed to regenerate'); setLoading(false); return; }
      const data = await res.json();
      setBackupCodes(data.backup_codes || []);
    } catch { setError('Network error.'); } finally { setLoading(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Two-Factor Authentication</h3>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </div>
        {step === 'show' && (
          <div className="space-y-4">
            {qr && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={qr} alt="QR code" className="mx-auto h-40 w-40" />
            )}
            {secret && (
              <div className="text-sm text-gray-700">
                <p className="font-medium">Secret (manual entry):</p>
                <p className="mt-1 break-all rounded bg-gray-50 p-2 border text-gray-800">{secret}</p>
              </div>
            )}
            <div>
              <label className="block text-xs text-gray-500 mb-1">Enter 6-digit code</label>
              <input
                className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !loading && code.trim().length >= 6) {
                    e.preventDefault();
                    void verify();
                  }
                }}
                placeholder="123 456"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
              <button className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-purple-300' : 'bg-[#7E22CE] hover:bg-[#7E22CE] active:bg-purple-900'}`} onClick={verify} disabled={loading}>
                {loading ? 'Verifying…' : 'Verify & Enable'}
              </button>
            </div>
          </div>
        )}
        {step === 'enabled' && (
          <div className="space-y-4">
            <p className="text-sm text-green-700">Two-factor authentication is now enabled.</p>
            {backupCodes && backupCodes.length > 0 && (
              <div className="text-sm text-gray-700">
                <p className="font-medium mb-1">Backup codes (store securely):</p>
                <ul className="list-disc pl-5 space-y-0.5">
                  {backupCodes.map((c) => (<li key={c} className="font-mono text-xs">{c}</li>))}
                </ul>
                <div className="mt-2 flex gap-2">
                  <button
                    className="rounded-md border px-3 py-1 text-xs hover:bg-gray-100 active:bg-gray-200 transition-colors"
                    onClick={() => { void navigator.clipboard.writeText(backupCodes.join('\n')); toast.success('Backup codes copied', {
                      style: {
                        background: '#6b21a8',
                        color: 'white',
                        border: 'none',
                        boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
                      },
                    }); }}
                  >
                    Copy
                  </button>
                  <button
                    className={`rounded-md border px-3 py-1 text-xs transition-colors ${loading ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-100 active:bg-gray-200'}`}
                    onClick={async () => { await regen(); toast.success('Backup codes regenerated', {
                      style: {
                        background: '#6b21a8',
                        color: 'white',
                        border: 'none',
                        boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
                      },
                    }); }}
                    disabled={loading}
                  >
                    {loading ? 'Working…' : 'Regenerate'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
        {step === 'disabled' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-700">Two-factor authentication has been disabled.</p>
            <div className="flex justify-end gap-3">
              <button autoFocus className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
            </div>
          </div>
        )}
        {step === 'enabled' && (
          <div className="mt-6 border-t pt-4 space-y-3">
            <p className="text-sm text-gray-700">To disable 2FA, confirm your password.</p>
            <input
              type="password"
              className="w-full rounded-md border px-3 py-2 text-sm"
              placeholder="Current password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !loading && currentPassword.trim().length > 0) {
                  e.preventDefault();
                  void disable();
                }
              }}
            />
            <div className="flex justify-end gap-3">
              <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
              <button className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-red-300' : 'bg-red-600 hover:bg-red-700 active:bg-red-800'}`} onClick={() => void disable()} disabled={loading}>
                {loading ? 'Disabling…' : 'Disable 2FA'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function StudentDashboard() {
  return (
    <Suspense fallback={<div className="min-h-screen" />}>
      <StudentDashboardContent />
    </Suspense>
  );
}

function AddressModal({ mode, address, onClose, onSaved }: { mode: 'create' | 'edit'; address?: SavedAddress; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    label: address?.label || 'home',
    street_line1: (address as Record<string, unknown>)?.['street_line1'] as string || '',
    street_line2: (address as Record<string, unknown>)?.['street_line2'] as string || '',
    locality: (address as Record<string, unknown>)?.['locality'] as string || '',
    administrative_area: (address as Record<string, unknown>)?.['administrative_area'] as string || '',
    postal_code: (address as Record<string, unknown>)?.['postal_code'] as string || '',
    country_code: (address as Record<string, unknown>)?.['country_code'] as string || 'US',
    is_default: !!address?.is_default,
    place_id: '',
  });
  const [query, setQuery] = useState('');
  type PlaceSuggestion = { place_id: string; provider?: string; description?: string; text?: string };
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const suppressAutocompleteRef = useRef(false);

  useEffect(() => {
    if (!query) {
      setSuggestions([]);
      return;
    }
    if (suppressAutocompleteRef.current) {
      // Skip one autocomplete cycle triggered by programmatic setQuery after selection
      suppressAutocompleteRef.current = false;
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetchWithAuth(`/api/addresses/places/autocomplete?q=${encodeURIComponent(query)}`);
        if (!res.ok) return;
        const data = await res.json();
        setSuggestions(data.items || []);
      } catch {}
    }, 250);
  }, [query]);

  const save = async () => {
    setLoading(true);
    try {
      const payload = { ...form } as Record<string, unknown>;
      // Trim empty strings
      Object.keys(payload).forEach((k) => { if (payload[k] === '') delete payload[k]; });
      const endpoint = mode === 'create' ? '/api/addresses/me' : `/api/addresses/me/${address?.id}`;
      const method = mode === 'create' ? 'POST' : 'PATCH';
      const res = await fetchWithAuth(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        const errorMessage = errorData?.detail || errorData?.message || 'Failed to save address';
        toast.error(errorMessage, {
          style: {
            background: '#fbbf24',
            color: '#000000',
            border: 'none',
          },
        });
        logger.error('Address save failed', { status: res.status, errorData, payload });
        setLoading(false);
        return;
      }
      toast.success('Address saved', {
        style: {
          background: '#6b21a8',
          color: 'white',
          border: 'none',
          boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
        },
      });
      onSaved();
    } catch (error) {
      toast.error('Network error', {
        style: {
          background: '#fbbf24',
          color: '#000000',
          border: 'none',
        },
      });
      logger.error('Address save network error', error as Error);
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl ring-1 ring-gray-200">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">{mode === 'create' ? 'Add Address' : 'Edit Address'}</h3>
          <p className="mt-1 text-sm text-gray-600">Add a saved address for quick booking.</p>
        </div>
        <div className="grid grid-cols-1 gap-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Label</label>
              <select className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-200" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}>
                <option value="home">Home</option>
                <option value="work">Work</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="flex items-center gap-2 mt-6">
              <input id="is_default" type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked })} />
              <label htmlFor="is_default" className="text-sm text-gray-700">Set as default</label>
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Address</label>
            <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-200" placeholder="Start typing…" value={query} onChange={(e) => { suppressAutocompleteRef.current = false; setQuery(e.target.value); }} />
            {suggestions.length > 0 && (
              <div className="mt-1 max-h-56 overflow-auto rounded-md border border-gray-200 bg-white text-sm shadow">
                {suggestions.map((s) => (
                  <button
                    key={s.place_id}
                    className="block w-full text-left px-3 py-2 hover:bg-gray-50"
                    onClick={async () => {
                      try {
                        // Fetch normalized place details and auto-fill fields
                        const providerQuery = s.provider ? `&provider=${encodeURIComponent(s.provider)}` : '';
                        const res = await fetchWithAuth(
                          `/api/addresses/places/details?place_id=${encodeURIComponent(s.place_id)}${providerQuery}`,
                        );
                        if (res.ok) {
                          const d = (await res.json()) as Record<string, unknown>;
                          const street = [d['street_number'], d['street_name']].filter(Boolean).join(' ');
                          setForm((prev) => ({
                            ...prev,
                            place_id: s.place_id,
                            street_line1: street || prev.street_line1,
                            locality: (d['city'] as string) || prev.locality,
                            administrative_area: (d['state'] as string) || prev.administrative_area,
                            postal_code: (d['postal_code'] as string) || prev.postal_code,
                          }));
                          suppressAutocompleteRef.current = true;
                          setQuery((d['formatted_address'] as string) || s.description || s.text || '');
                        } else {
                          setForm((prev) => ({ ...prev, place_id: s.place_id }));
                          suppressAutocompleteRef.current = true;
                          setQuery(s.description || s.text || '');
                        }
                      } catch {
                        setForm((prev) => ({ ...prev, place_id: s.place_id }));
                        suppressAutocompleteRef.current = true;
                        setQuery(s.description || s.text || '');
                      }
                      setSuggestions([]);
                    }}
                  >
                    {s.description || s.text}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Address line 1</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-200" value={form.street_line1} onChange={(e) => setForm({ ...form, street_line1: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Address line 2</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-200" value={form.street_line2} onChange={(e) => setForm({ ...form, street_line2: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">City</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-200" value={form.locality} onChange={(e) => setForm({ ...form, locality: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">State</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-200" value={form.administrative_area} onChange={(e) => setForm({ ...form, administrative_area: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Postal code</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-200" value={form.postal_code} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} />
            </div>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button className="rounded-md border border-gray-200 px-4 py-2 text-sm" onClick={onClose} disabled={loading}>Cancel</button>
          <button className={`rounded-md px-4 py-2 text-sm text-white ${loading ? 'bg-purple-300' : 'bg-[#7E22CE] hover:bg-[#7E22CE]'}`} onClick={save} disabled={loading}>
            {loading ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Local modal components
function DeleteAccountModal({ email, onClose, onDeleted }: { email: string; onClose: () => void; onDeleted: () => void }) {
  const [password, setPassword] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const canSubmit = confirmText.trim().toUpperCase() === 'DELETE' && password.length >= 6 && !submitting;

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Verify password silently (backend expects form-encoded OAuth2 fields)
      const loginRes = await fetchAPI(API_ENDPOINTS.LOGIN, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password }).toString(),
      });
      if (!loginRes.ok) {
        setError('Incorrect password.');
        setSubmitting(false);
        return;
      }

      // Soft delete account
      const delRes = await fetchWithAuth('/api/privacy/delete/me', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delete_account: true }),
      });
      if (!delRes.ok) {
        try {
          const body = await delRes.json();
          if (delRes.status === 400 && body?.detail) {
            setError(body.detail);
          } else {
            setError('Failed to delete account. Please try again later.');
          }
        } catch {
          setError('Failed to delete account. Please try again later.');
        }
        setSubmitting(false);
        return;
      }
      onDeleted();
    } catch {
      setError('Unexpected error. Please try again.');
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Delete Account</h3>
          <p className="mt-2 text-sm text-gray-600">This action cannot be undone. Type DELETE to confirm and enter your password.</p>
        </div>
        <div className="space-y-3">
          <input
            placeholder="Type DELETE to confirm"
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
          />
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder="Password"
              className="w-full rounded-md border px-3 py-2 pr-10 text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors" onClick={onClose} disabled={submitting}>Cancel</button>
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium border ${canSubmit ? 'bg-white border-[#7E22CE] text-[#7E22CE] hover:bg-purple-50' : 'bg-gray-100 border-gray-300 text-gray-400 cursor-not-allowed'}`}
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {submitting ? 'Deleting…' : 'Delete My Account'}
          </button>
        </div>
      </div>
    </div>
  );
}

function EditProfileModal({ user, onClose, onSaved }: { user: Record<string, unknown>; onClose: () => void; onSaved: () => void }) {
  // Debug log to see what user data we're getting
  logger.debug('EditProfileModal received user data', {
    fullUser: user,
    first_name: user?.['first_name'],
    last_name: user?.['last_name'],
    phone: user?.['phone'],
    zip_code: user?.['zip_code']
  });

  const [firstName, setFirstName] = useState<string>(
    typeof (user as unknown as { first_name?: unknown })?.first_name === 'string'
      ? ((user as unknown as { first_name?: string }).first_name as string)
      : ''
  );
  const [lastName, setLastName] = useState<string>(
    typeof (user as unknown as { last_name?: unknown })?.last_name === 'string'
      ? ((user as unknown as { last_name?: string }).last_name as string)
      : ''
  );
  const [phone, setPhone] = useState<string>(
    typeof (user as unknown as { phone?: unknown })?.phone === 'string'
      ? ((user as unknown as { phone?: string }).phone as string)
      : ''
  );
  const [zipCode, setZipCode] = useState<string>(
    typeof (user as unknown as { zip_code?: unknown })?.zip_code === 'string'
      ? ((user as unknown as { zip_code?: string }).zip_code as string)
      : ''
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  logger.debug('Initial state values set');

  const handleSubmit = async () => {
    setError('');
    setLoading(true);

    const updateData = {
      first_name: firstName,
      last_name: lastName,
      phone,
      zip_code: zipCode,
    };

    logger.info('Submitting profile update');

    try {
      const res = await fetchWithAuth('/auth/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updateData),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        logger.error('Profile update failed', new Error(String(res.status)), { body });
        setError(body.detail || 'Failed to update profile');
        setLoading(false);
        return;
      }

      await res.json();
      logger.info('Profile update successful');

      toast.success('Profile updated successfully', {
        style: {
          background: '#6b21a8',
          color: 'white',
          border: 'none',
          boxShadow: '0 10px 15px -3px rgba(124, 58, 237, 0.1), 0 4px 6px -2px rgba(124, 58, 237, 0.05)',
        },
      });

      setLoading(false);
      onSaved();
    } catch (err) {
      logger.error('Profile update error', err as Error);
      setError('Network error. Please try again.');
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-xl font-bold text-gray-900 mb-6">Edit Profile</h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
            <input
              type="text"
              value={firstName}
              onChange={(e) => {
                logger.debug('First name changing');
                setFirstName(e.target.value);
              }}
              onFocus={() => logger.debug('First name input focused')}
              placeholder="Enter first name"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/25 focus:border-purple-500"
            />
            <p className="text-xs text-gray-500 mt-1">Current value: {firstName || '(empty)'}</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/25 focus:border-purple-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="(555) 123-4567"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/25 focus:border-purple-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">ZIP Code</label>
            <input
              type="text"
              value={zipCode}
              onChange={(e) => setZipCode(e.target.value)}
              placeholder="10001"
              maxLength={5}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/25 focus:border-purple-500"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            onClick={onClose}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors ${
              loading
                ? 'bg-purple-400 cursor-not-allowed'
                : 'bg-[#7E22CE] hover:bg-[#7E22CE]'
            }`}
            onClick={handleSubmit}
            disabled={loading}
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showPasswords, setShowPasswords] = useState(false);

  const canSubmit = newPassword.length >= 8 && newPassword === confirmPassword && currentPassword.length >= 6 && !submitting;

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Call in-app change password endpoint
      const res = await fetchWithAuth('/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.detail || 'Failed to change password.');
        setSubmitting(false);
        return;
      }
      setStatus('Password changed successfully.');
      setSubmitting(false);
    } catch {
      setError('Unexpected error. Please try again.');
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Change Password</h3>
        </div>
        <div className="space-y-3">
          <div className="relative">
            <input
              type={showPasswords ? 'text' : 'password'}
              placeholder="Current password"
              className="w-full rounded-md border px-3 py-2 text-sm pr-10"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
            <button
              type="button"
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
              onClick={() => setShowPasswords((v) => !v)}
              aria-label={showPasswords ? 'Hide passwords' : 'Show passwords'}
            >
              {showPasswords ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
            </button>
          </div>
          <div className="relative">
            <input
              type={showPasswords ? 'text' : 'password'}
              placeholder="New password"
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </div>
          <div className="relative">
            <input
              type={showPasswords ? 'text' : 'password'}
              placeholder="Confirm new password"
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {status && <p className="text-sm text-green-600">{status}</p>}
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors" onClick={onClose} disabled={submitting}>Cancel</button>
          <button
            className={`rounded-md px-4 py-2 text-sm text-white ${canSubmit ? 'bg-[#7E22CE] hover:bg-[#7E22CE]' : 'bg-purple-300 cursor-not-allowed'}`}
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            {submitting ? 'Submitting…' : 'Change Password'}
          </button>
        </div>
      </div>
    </div>
  );
}
