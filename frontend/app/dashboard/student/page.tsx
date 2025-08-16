// frontend/app/dashboard/student/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { LogOut, Heart, User, CreditCard, Bell, Eye, EyeOff } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';
import { logger } from '@/lib/logger';
import { useAuth, hasRole, type User as AuthUser } from '@/features/shared/hooks/useAuth';
import { RoleName } from '@/types/enums';
import { getUserFullName, getUserInitials } from '@/types/user';
import { fetchAPI, fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { toast } from 'sonner';

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
  const [referralEmails, setReferralEmails] = useState('');
  const [referralStatus, setReferralStatus] = useState('');

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

  // Loading state
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (!userData) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="text-2xl font-bold text-indigo-600">
              {BRAND.name}
            </Link>
            <button
              onClick={handleLogout}
              className="flex items-center text-gray-600 hover:text-gray-900 transition-colors"
            >
              <LogOut className="h-5 w-5 mr-2" />
              Log out
            </button>
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
                      `w-full flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium mb-1 transition-colors ` +
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

                  {/* Addresses (placeholder) */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-lg font-semibold text-gray-900">Addresses</h3>
                      <button className="text-sm font-medium text-indigo-600 hover:text-indigo-700">+ Add</button>
                    </div>
                    <div className="grid grid-cols-1 gap-3">
                      <div className="rounded-md border p-4">
                        <p className="font-medium text-gray-900">Home (Default)</p>
                        <p className="text-sm text-gray-600">123 Main St, Apt 4B, New York, NY 10023</p>
                        <div className="mt-2 flex gap-3 text-sm">
                          <button className="text-indigo-600 hover:text-indigo-700">Edit</button>
                          <button className="text-gray-500 hover:text-gray-700">Remove</button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Security (placeholder) */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Security</h3>
                    <div className="flex flex-wrap gap-3">
                      <button
                        className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-200"
                        onClick={() => setShowChangePassword(true)}
                      >
                        Change Password
                      </button>
                      <button className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-800 hover:bg-gray-200" disabled>
                        Enable Two-Factor Authentication
                      </button>
                    </div>
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
                        className="h-10 min-w-[120px] inline-flex items-center justify-center rounded-md bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-700"
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
                        className="h-10 min-w-[120px] inline-flex items-center justify-center rounded-md bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-700"
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
                        className="rounded-md border border-red-300 text-red-700 px-4 py-2 text-sm font-medium hover:bg-red-50"
                        onClick={() => setShowDelete(true)}
                      >
                        Delete Account
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab !== 'profile' && (
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

// Local modal components
function DeleteAccountModal({ email, onClose, onDeleted }: { email: string; onClose: () => void; onDeleted: () => void }) {
  const [password, setPassword] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = confirmText.trim().toUpperCase() === 'DELETE' && password.length >= 6 && !submitting;

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Verify password silently
      const loginRes = await fetchAPI(API_ENDPOINTS.LOGIN, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (!loginRes.ok) {
        setError('Incorrect password.');
        setSubmitting(false);
        return;
      }

      // Soft delete account
      const delRes = await fetchWithAuth('/privacy/delete/me', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ delete_account: true }),
      });
      if (!delRes.ok) {
        setError('Failed to delete account. Please try again later.');
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
          <input
            type="password"
            placeholder="Password"
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
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
