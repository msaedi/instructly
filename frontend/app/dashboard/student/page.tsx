// frontend/app/dashboard/student/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { LogOut, Heart, User, CreditCard, Bell, Eye, EyeOff, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';
import { logger } from '@/lib/logger';
import { useAuth, hasRole, type User as AuthUser } from '@/features/shared/hooks/useAuth';
import { RoleName } from '@/types/enums';
import { getUserFullName, getUserInitials } from '@/types/user';
import { fetchAPI, fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { toast } from 'sonner';
import { favoritesApi } from '@/services/api/favorites';
import type { FavoritedInstructor } from '@/types/instructor';
import UserProfileDropdown from '@/components/UserProfileDropdown';

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
 * // Route: /dashboard/student
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
  const [referralEmails, setReferralEmails] = useState('');
  const [referralStatus, setReferralStatus] = useState('');
  const [addresses, setAddresses] = useState<any[] | null>(null);
  const [isLoadingAddresses, setIsLoadingAddresses] = useState(false);
  const [showAddressModal, setShowAddressModal] = useState<null | { mode: 'create' } | { mode: 'edit'; address: any }>(null);
  const [tfaStatus, setTfaStatus] = useState<{ enabled: boolean; verified_at?: string | null; last_used_at?: string | null } | null>(null);

  const tabs = useMemo(
    () => [
      { key: 'profile', label: 'Profile', icon: User },
      { key: 'billing', label: 'Billing', icon: CreditCard },
      { key: 'notifications', label: 'Notifications', icon: Bell },
      { key: 'favorites', label: 'Favorites', icon: Heart },
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
  } = useQuery<AuthUser>({
    queryKey: queryKeys.user,
    queryFn: queryFn('/auth/me', { requireAuth: true }),
    staleTime: CACHE_TIMES.SESSION, // Session-long cache
    retry: false,
  });

  const isLoading = isLoadingUser;

  // Favorites data (loaded lazily when the tab is active)
  const {
    data: favoritesData,
    isLoading: isLoadingFavorites,
    error: favoritesError,
    refetch: refetchFavorites,
  } = useQuery<{ favorites: FavoritedInstructor[]; total: number }>({
    queryKey: ['favorites'],
    queryFn: favoritesApi.list,
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      router.push('/dashboard/instructor');
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
      const v = ALPH.indexOf(ulid[i]);
      if (v === -1) return null;
      ts = ts * 32 + v;
    }
    return new Date(ts);
  };

  const memberSince = decodeUlidTimestamp(userData?.id || '');

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
    } catch (e) {
      setAddresses([]);
    } finally {
      setIsLoadingAddresses(false);
    }
  };

  useEffect(() => {
    loadAddresses();
    // Preload TFA status in background
    (async () => {
      try {
        const res = await fetchWithAuth('/api/auth/2fa/status');
        if (res.ok) {
          const data = await res.json();
          setTfaStatus({ enabled: !!data.enabled, verified_at: data.verified_at || null, last_used_at: data.last_used_at || null });
        }
      } catch {}
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-700"></div>
      </div>
    );
  }

  if (!userData) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="flex justify-between items-center h-16">
          <Link href="/" className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors pl-4">
            iNSTAiNSTRU
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Stats bar (dismissible) */}
        {isStatsVisible && (
          <div className="mb-6 flex items-start justify-between gap-4 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-yellow-800">
            <div className="text-sm">
              <span className="font-medium">You've completed 12 lessons this year.</span> 3 more to reach Bronze status!
            </div>
            <button
              aria-label="Dismiss"
              className="text-yellow-700 hover:text-yellow-900"
              onClick={() => setIsStatsVisible(false)}
            >
              ×
            </button>
          </div>
        )}

        <h1 className="text-2xl font-bold text-gray-900 mb-6">Your Account</h1>

        <div className="grid grid-cols-12 gap-6">
          {/* Sidebar tabs */}
          <aside className="col-span-12 md:col-span-3">
            <div className="bg-white rounded-lg border shadow-sm p-2">
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
                      `w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium mb-1 transition-colors cursor-pointer ` +
                      (isActive
                        ? 'bg-indigo-50 text-indigo-700'
                        : 'text-gray-700 hover:bg-gray-50')
                    }
                  >
                    <Icon className="h-4 w-4" />
                    <span>{label}</span>
                  </button>
                );
              })}
            </div>
          </aside>

        {/* Main content */}
          <section className="col-span-12 md:col-span-9">
            <div className="bg-white rounded-lg border shadow-sm p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900">
                  {tabs.find(t => t.key === activeTab)?.label}
                </h2>
              </div>

              {activeTab === 'profile' && (
                <div className="space-y-8">
                  {/* Account Information */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Account Information</h3>
                    <div className="flex items-start gap-5">
                      <div className="h-20 w-20 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-2xl font-bold shrink-0">
                        {getUserInitials(userData)}
                      </div>
                      <div className="space-y-1.5 text-sm text-gray-700">
                        <p className="text-base font-semibold text-gray-900">{getUserFullName(userData)}</p>
                        <p>{userData.email}</p>
                        <p>{formatPhoneReadable((userData as any).phone)}</p>
                        <p>
                          {(() => {
                            const z = (userData as any).zip_code;
                            const info = inferCityStateFromZip(z);
                            return info ? `${info.city}, ${info.state}, ${z}` : z || '—';
                          })()}
                        </p>
                        <p className="text-indigo-700/90">
                          Member since: {memberSince ? memberSince.toLocaleDateString('en-US', { month: 'long', year: 'numeric' }) : '—'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Achievements (placeholder) */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Achievements</h3>
                    <div className="flex flex-wrap gap-2">
                      <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">🥉 5 Lessons</span>
                      <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">🎯 Quick Learner</span>
                      <span className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800">⭐ Top Student</span>
                    </div>
                  </div>

                  {/* Addresses */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-lg font-semibold text-gray-900">Addresses</h3>
                      <button
                        className="text-sm font-medium text-indigo-600 hover:text-indigo-700 cursor-pointer"
                        onClick={() => setShowAddressModal({ mode: 'create' })}
                      >
                        + Add
                      </button>
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      {isLoadingAddresses && (
                        <div className="rounded-md border p-4 text-sm text-gray-600">Loading addresses…</div>
                      )}
                      {!isLoadingAddresses && (addresses?.length || 0) === 0 && (
                        <div className="rounded-md border p-4 text-sm text-gray-600">No addresses added yet.</div>
                      )}
                      {!isLoadingAddresses && (addresses || []).map((a) => (
                        <div key={a.id} className="rounded-md border p-4">
                          <p className="font-medium text-gray-900">
                            {(a.label ? a.label.charAt(0).toUpperCase() + a.label.slice(1) : 'Address')} {a.is_default ? '(Default)' : ''}
                          </p>
                          <p className="text-sm text-gray-600">
                            {[a.street_line1, a.street_line2].filter(Boolean).join(', ')}{[a.locality, a.administrative_area].some(Boolean) ? `, ${[a.locality, a.administrative_area].filter(Boolean).join(', ')}` : ''}{a.postal_code ? `, ${a.postal_code}` : ''}
                          </p>
                          <div className="mt-2 flex gap-3 text-sm">
                            <button
                              className="text-indigo-600 hover:text-indigo-700"
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
                                      <button id="confirmBtn" class="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700">Remove</button>
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
                                  toast.success('Address removed');
                                  loadAddresses();
                                } else {
                                  toast.error('Failed to remove address');
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
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Security</h3>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-200 cursor-pointer"
                        onClick={() => setShowChangePassword(true)}
                      >
                        Change Password
                      </button>
                      <button
                        className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-200 cursor-pointer"
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

                  {/* Referral Program (mock) */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Referral Program</h3>
                    <p className="text-sm text-gray-600 mb-4">
                      Help your friends learn! They get $20 off their first lesson. You get $20 credit when they complete it.
                    </p>
                    <div className="flex items-center gap-3">
                      <input
                        type="text"
                        placeholder="Enter email addresses..."
                        className="h-10 w-full rounded-md appearance-none shadow-none ring-1 ring-gray-300/70 border-0 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500/25 focus:border-0"
                        onChange={(e) => setReferralEmails(e.target.value)}
                        value={referralEmails}
                      />
                      <button
                        className="h-10 min-w-[120px] inline-flex items-center justify-center rounded-md bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-700 cursor-pointer"
                        onClick={async () => {
                          const emails = referralEmails
                            .split(/[\s,;]+/)
                            .map((e) => e.trim())
                            .filter((e) => e.length > 0);
                          if (emails.length === 0) {
                            toast.error('Please enter at least one email');
                            return;
                          }
                          const invalid = emails.filter((e) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));
                          if (invalid.length > 0) {
                            toast.error(`Invalid email: ${invalid[0]}`);
                            return;
                          }
                          const link = `https://instainstru.com/ref/${(userData?.first_name || 'USER').toUpperCase().slice(0, 3)}${(userData?.id || '').slice(-3)}`;
                          try {
                            const res = await fetchAPI('/api/public/referrals/send', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ emails, referral_link: link, from_name: userData?.first_name || 'A friend' }),
                            });
                            if (!res.ok) {
                              const body = await res.json().catch(() => ({}));
                              toast.error(body.detail || 'Failed to send invites');
                              return;
                            }
                            const data = await res.json().catch(() => ({}));
                            toast.success(`Invites sent to ${data.count || emails.length} recipient(s)`);
                            setReferralEmails('');
                          } catch (e) {
                            toast.error('Network error while sending invites');
                          }
                        }}
                      >
                        Send Invite
                      </button>
                    </div>
                    <div className="mt-3 flex items-center gap-3">
                      <input
                        readOnly
                        className="h-10 w-full rounded-md appearance-none shadow-none ring-1 ring-gray-300/70 border-0 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-indigo-500/25 focus:border-0"
                        value={`https://instainstru.com/ref/${(userData?.first_name || 'USER').toUpperCase().slice(0, 3)}${(userData?.id || '').slice(-3)}`}
                      />
                      <button
                        className="h-10 min-w-[120px] inline-flex items-center justify-center rounded-md bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-700 cursor-pointer"
                        onClick={() => {
                          const link = `https://instainstru.com/ref/${(userData?.first_name || 'USER').toUpperCase().slice(0, 3)}${(userData?.id || '').slice(-3)}`;
                          navigator.clipboard.writeText(link);
                          setReferralStatus('Referral link copied');
                          setTimeout(() => setReferralStatus(''), 2000);
                        }}
                      >
                        Copy Link
                      </button>
                    </div>
                    {referralStatus && (
                      <p className="mt-2 text-sm text-green-600">{referralStatus}</p>
                    )}
                  </div>

                  {/* Account Management (placeholder) */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Account Management</h3>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="rounded-md border border-red-300 text-red-700 px-4 py-2 text-sm font-medium hover:bg-red-50 cursor-pointer"
                        onClick={() => setShowDelete(true)}
                      >
                        Delete Account
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'favorites' && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">Quickly access your favorite subjects and instructors</p>

                  {isLoadingFavorites && (
                    <div className="rounded-md border p-4 text-sm text-gray-600">Loading favorites…</div>
                  )}

                  {!isLoadingFavorites && favoritesError && (
                    <div className="rounded-md border p-4 text-sm text-red-600">Failed to load favorites.</div>
                  )}

                  {!isLoadingFavorites && !favoritesError && (favoritesData?.favorites?.length || 0) === 0 && (
                    <div className="rounded-md border p-6 text-sm text-gray-700 flex items-center justify-between">
                      <div>No favorite instructors yet.</div>
                      <Link href="/" className="rounded-md bg-indigo-600 px-4 py-2 text-white text-sm hover:bg-indigo-700">Find More Instructors</Link>
                    </div>
                  )}

                  {!isLoadingFavorites && !favoritesError && (favoritesData?.favorites?.length || 0) > 0 && (
                    <div className="grid grid-cols-1 gap-4">
                      {favoritesData!.favorites.map((fav) => {
                        const name = fav.profile?.user
                          ? `${fav.profile.user.first_name} ${fav.profile.user.last_initial ? fav.profile.user.last_initial + '.' : ''}`
                          : `${fav.first_name}${fav.last_name ? ' ' + fav.last_name.charAt(0) + '.' : ''}`;
                        const services = fav.profile?.services || [];
                        const uniqueServices = Array.from(new Set(services.map(s => (s.skill || '').split(' - ')[0]).filter(Boolean)));
                        const primaryRate = services?.[0]?.hourly_rate;
                        const primarySubject = uniqueServices[0] || null;
                        const primaryArea = fav.profile?.areas_of_service?.[0] || null;
                        const yearsExp = fav.profile?.years_experience || null;

                        return (
                          <div
                            key={fav.id}
                            className="relative rounded-md border p-4 pr-10 hover:bg-gray-50 transition-colors cursor-pointer"
                            onClick={() => router.push(`/instructors/${fav.id}`)}
                          >
                            <div className="flex items-start gap-4">
                              <div className="h-12 w-12 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-lg font-bold shrink-0">👤</div>
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
                                  toast.success('Removed from favorites');
                                  await refetchFavorites();
                                } catch (e) {
                                  toast.error('Failed to update favorite');
                                }
                              }}
                            >
                              <X className="h-4 w-4" />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {activeTab !== 'profile' && activeTab !== 'favorites' && (
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
          email={(userData as any).email}
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
          email={(userData as any).email}
          onClose={() => setShowChangePassword(false)}
        />
      )}

      {showAddressModal && (
        <AddressModal
          mode={showAddressModal.mode}
          address={(showAddressModal as any).address}
          onClose={() => setShowAddressModal(null)}
          onSaved={() => {
            setShowAddressModal(null);
            loadAddresses();
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
      if (!res.ok) { const b = await res.json().catch(() => ({})); setError(b.detail || 'That code didn’t work. Please try again.'); setLoading(false); return; }
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
            {qr && <img src={qr} alt="QR code" className="mx-auto h-40 w-40" />}
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
                    verify();
                  }
                }}
                placeholder="123 456"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
              <button className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-indigo-300' : 'bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800'}`} onClick={verify} disabled={loading}>
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
                    onClick={() => { navigator.clipboard.writeText(backupCodes.join('\n')); toast.success('Backup codes copied'); }}
                  >
                    Copy
                  </button>
                  <button
                    className={`rounded-md border px-3 py-1 text-xs transition-colors ${loading ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-100 active:bg-gray-200'}`}
                    onClick={async () => { await regen(); toast.success('Backup codes regenerated'); }}
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
                  disable();
                }
              }}
            />
            <div className="flex justify-end gap-3">
              <button className="rounded-md border px-4 py-2 text-sm hover:bg-gray-100 active:bg-gray-200 transition-colors" onClick={onClose}>Close</button>
              <button className={`rounded-md px-4 py-2 text-sm text-white transition-colors ${loading ? 'bg-red-300' : 'bg-red-600 hover:bg-red-700 active:bg-red-800'}`} onClick={disable} disabled={loading}>
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

function AddressModal({ mode, address, onClose, onSaved }: { mode: 'create' | 'edit'; address?: any; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    label: address?.label || 'home',
    street_line1: address?.street_line1 || '',
    street_line2: address?.street_line2 || '',
    locality: address?.locality || '',
    administrative_area: address?.administrative_area || '',
    postal_code: address?.postal_code || '',
    country_code: address?.country_code || 'US',
    is_default: !!address?.is_default,
    place_id: '',
  });
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<any>(null);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const save = async () => {
    setLoading(true);
    try {
      const payload = { ...form } as any;
      // Trim empty strings
      Object.keys(payload).forEach((k) => { if (payload[k] === '') delete payload[k]; });
      const endpoint = mode === 'create' ? '/api/addresses/me' : `/api/addresses/me/${address.id}`;
      const method = mode === 'create' ? 'POST' : 'PATCH';
      const res = await fetchWithAuth(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        toast.error('Failed to save address');
        setLoading(false);
        return;
      }
      toast.success('Address saved');
      onSaved();
    } catch {
      toast.error('Network error');
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
              <select className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}>
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
            <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" placeholder="Start typing…" value={query} onChange={(e) => { suppressAutocompleteRef.current = false; setQuery(e.target.value); }} />
            {suggestions.length > 0 && (
              <div className="mt-1 max-h-56 overflow-auto rounded-md border border-gray-200 bg-white text-sm shadow">
                {suggestions.map((s) => (
                  <button
                    key={s.place_id}
                    className="block w-full text-left px-3 py-2 hover:bg-gray-50"
                    onClick={async () => {
                      try {
                        // Fetch normalized place details and auto-fill fields
                        const res = await fetchWithAuth(`/api/addresses/places/details?place_id=${encodeURIComponent(s.place_id)}`);
                        if (res.ok) {
                          const d = await res.json();
                          const street = [d.street_number, d.street_name].filter(Boolean).join(' ');
                          setForm((prev) => ({
                            ...prev,
                            place_id: s.place_id,
                            street_line1: street || prev.street_line1,
                            locality: d.city || prev.locality,
                            administrative_area: d.state || prev.administrative_area,
                            postal_code: d.postal_code || prev.postal_code,
                          }));
                          suppressAutocompleteRef.current = true;
                          setQuery(d.formatted_address || s.description || s.text);
                        } else {
                          setForm((prev) => ({ ...prev, place_id: s.place_id }));
                          suppressAutocompleteRef.current = true;
                          setQuery(s.description || s.text);
                        }
                      } catch {
                        setForm((prev) => ({ ...prev, place_id: s.place_id }));
                        suppressAutocompleteRef.current = true;
                        setQuery(s.description || s.text);
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
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" value={form.street_line1} onChange={(e) => setForm({ ...form, street_line1: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Address line 2</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" value={form.street_line2} onChange={(e) => setForm({ ...form, street_line2: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">City</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" value={form.locality} onChange={(e) => setForm({ ...form, locality: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">State</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" value={form.administrative_area} onChange={(e) => setForm({ ...form, administrative_area: e.target.value })} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Postal code</label>
              <input className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" value={form.postal_code} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} />
            </div>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button className="rounded-md border border-gray-200 px-4 py-2 text-sm" onClick={onClose} disabled={loading}>Cancel</button>
          <button className={`rounded-md px-4 py-2 text-sm text-white ${loading ? 'bg-indigo-300' : 'bg-indigo-600 hover:bg-indigo-700'}`} onClick={save} disabled={loading}>
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
    } catch (e) {
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
          <button className="rounded-md border px-4 py-2 text-sm" onClick={onClose} disabled={submitting}>Cancel</button>
          <button
            className={`rounded-md px-4 py-2 text-sm text-white ${canSubmit ? 'bg-red-600 hover:bg-red-700' : 'bg-red-300 cursor-not-allowed'}`}
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

function ChangePasswordModal({ email, onClose }: { email: string; onClose: () => void }) {
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
    } catch (e) {
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
          <button className="rounded-md border px-4 py-2 text-sm" onClick={onClose} disabled={submitting}>Cancel</button>
          <button
            className={`rounded-md px-4 py-2 text-sm text-white ${canSubmit ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-indigo-300 cursor-not-allowed'}`}
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
