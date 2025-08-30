// frontend/app/(auth)/instructor/dashboard/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { Edit, Calendar, ExternalLink, LogOut, Trash2, CheckCircle2, XCircle } from 'lucide-react';
import EditProfileModal from '@/components/modals/EditProfileModal';
import DeleteProfileModal from '@/components/modals/DeleteProfileModal';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { logger } from '@/lib/logger';
import { InstructorProfile, getInstructorDisplayName } from '@/types/instructor';
import { useAuth } from '@/features/shared/hooks/useAuth';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import StripeOnboarding from '@/components/instructor/StripeOnboarding';

export default function InstructorDashboardNew() {
  const router = useRouter();
  const { logout } = useAuth();
  const [profile, setProfile] = useState<InstructorProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [connectStatus, setConnectStatus] = useState<any>(null);
  const [isMounted, setIsMounted] = useState(false);
  const [isStartingStripeOnboarding, setIsStartingStripeOnboarding] = useState(false);

  const fetchProfile = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      logger.warn('No access token found, redirecting to login');
      router.push('/login?redirect=/instructor/dashboard');
      return;
    }

    try {
      logger.info('Fetching instructor profile');
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);

      if (response.status === 404) {
        logger.warn('No instructor profile found');
        setError('No instructor profile found. Please complete your profile setup.');
        setIsLoading(false);
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to fetch profile');
      }

      const data: InstructorProfile = await response.json();
      if (!data.user || !data.services) {
        logger.error('Invalid profile data structure', undefined, { data });
        throw new Error('Invalid profile data received');
      }

      logger.info('Instructor profile loaded successfully', {
        userId: data.user_id,
        servicesCount: data.services.length,
        areasCount: data.areas_of_service?.length || 0,
      });

      setProfile(data);
    } catch (err) {
      logger.error('Error fetching instructor profile', err);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    setIsMounted(true);
    logger.info('Instructor dashboard (new) loaded');
    fetchProfile();
    (async () => {
      try {
        const s = await getConnectStatus();
        setConnectStatus(s);
      } catch (e) {
        logger.warn('Failed to load connect status');
      }
    })();
  }, [router]);

  // Gate access until cleared to go live
  useEffect(() => {
    if (!profile || connectStatus == null) return;
    const isLive = Boolean(profile.is_live);
    if (isLive) return; // Never redirect live instructors
    const skillsOk = (profile.skills_configured === true) || (Array.isArray(profile.services) && profile.services.length > 0);
    const identityOk = Boolean(profile.identity_verified_at || profile.identity_verification_session_id);
    const connectOk = Boolean(connectStatus?.charges_enabled && connectStatus?.details_submitted);
    const ready = skillsOk && identityOk && connectOk;
    if (!ready) {
      logger.info('Redirecting to onboarding status - prerequisites not complete');
      router.replace('/instructor/onboarding/status');
    }
  }, [profile, connectStatus, router]);

  const handleLogout = () => {
    logger.info('Instructor logging out');
    logout();
  };

  const handleProfileUpdate = () => {
    logger.info('Profile updated, refreshing data');
    fetchProfile();
    setShowEditModal(false);
  };

  const handleProfileDelete = () => {
    logger.info('Instructor profile deleted, logging out and redirecting home');
    logout();
    router.push('/');
  };

  const handleViewPublicProfile = () => {
    if (profile) {
      logger.debug('Navigating to public profile', { userId: profile.user_id });
      router.push(`/instructors/${profile.user_id}`);
    }
  };

  // After mount, show a client-rendered spinner while loading
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-700" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen">
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <a href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </a>
            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
          <div className="bg-white rounded-lg border border-gray-200 p-6 text-center">
            <h2 className="text-2xl font-bold text-red-600 mb-4">Error</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <Link
              href="/signup?redirect=%2Finstructor%2Fonboarding%2Fstep-2"
              className="inline-block px-6 py-2.5 bg-purple-700 text-white rounded-lg hover:bg-purple-800 transition-colors"
              onClick={() => logger.debug('Navigating to signup with redirect to step-2 from error state')}
            >
              Complete Profile Setup
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!profile) return null;

  const displayName = getInstructorDisplayName(profile);

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <a href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </a>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <h1 className="text-3xl font-bold text-gray-600 mb-2">Welcome back, {profile.user?.first_name || 'Instructor'}!</h1>
          <p className="text-gray-600">Manage your instructor profile and payouts</p>
        </div>

        {/* Quick Actions */}
        <div className="mb-6 flex flex-wrap gap-4">
          <Link
            href="/instructor/availability"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <Calendar className="h-4 w-4" />
            <span>Manage Availability</span>
          </Link>
          <Link
            href="/instructor/bookings"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <Calendar className="h-4 w-4" />
            <span>View Bookings</span>
          </Link>
          <button
            onClick={handleViewPublicProfile}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            <span>View Public Profile</span>
          </button>
        </div>

        <div className="mb-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Stripe Status Card */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-purple-600 via-purple-500 to-indigo-500 px-6 py-4">
              <h2 className="text-lg font-semibold text-white">Stripe Account</h2>
              <p className="text-purple-100 text-xs mt-0.5">Manage onboarding and payouts</p>
            </div>
            <div className="p-6">
              <p className="text-gray-600 text-sm mb-4">Your Stripe account setup status.</p>
            {connectStatus ? (() => {
              const chargesEnabled = Boolean(connectStatus?.charges_enabled);
              const payoutsEnabled = Boolean(connectStatus?.payouts_enabled);
              const detailsSubmitted = Boolean(connectStatus?.details_submitted);
              // Compute UI completion from live signals rather than trusting stale flag
              const onboardingCompleted = Boolean(chargesEnabled && detailsSubmitted);
              const allGood = chargesEnabled && payoutsEnabled && detailsSubmitted && onboardingCompleted;
              const wrapperClass = allGood
                ? 'rounded-lg border border-green-200 bg-green-50 p-4'
                : 'rounded-lg border border-amber-200 bg-amber-50 p-4';
              return (
                <div className={wrapperClass}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <ChecklistRow label="Charges enabled" ok={chargesEnabled} />
                    <ChecklistRow label="Payouts enabled" ok={payoutsEnabled} />
                    <ChecklistRow label="Details verified" ok={detailsSubmitted} />
                    <ChecklistRow label="Onboarding completed" ok={onboardingCompleted} />
                  </div>
                </div>
              );
            })() : (
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="h-6 w-40 bg-gray-100 rounded mb-2" />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="h-10 bg-gray-100 rounded" />
                  <div className="h-10 bg-gray-100 rounded" />
                  <div className="h-10 bg-gray-100 rounded" />
                  <div className="h-10 bg-gray-100 rounded" />
                </div>
              </div>
            )}
            <div className="mt-5 flex gap-3">
              <button
                onClick={async () => {
                  try { const s = await getConnectStatus(); setConnectStatus(s); } catch {}
                }}
                className="inline-flex items-center px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
              >
                <ExternalLink className="w-4 h-4 mr-2 rotate-90" /> Refresh Status
              </button>
              {connectStatus && !(Boolean(connectStatus?.charges_enabled) && Boolean(connectStatus?.details_submitted)) && (
                <button
                  onClick={async () => {
                    try {
                      setIsStartingStripeOnboarding(true);
                      const retPath = '/instructor/dashboard?stripe_onboarding_return=true';
                      const resp = await paymentService.startOnboardingWithReturn(retPath);
                      if (resp?.onboarding_url) {
                        window.location.href = resp.onboarding_url;
                      } else {
                        alert('Could not start Stripe onboarding.');
                      }
                    } catch (e) {
                      alert('Unable to start Stripe onboarding right now.');
                    } finally {
                      setIsStartingStripeOnboarding(false);
                    }
                  }}
                  disabled={isStartingStripeOnboarding}
                  className="inline-flex items-center px-3 py-2 text-sm rounded-md border border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100 disabled:opacity-60"
                >
                  {isStartingStripeOnboarding ? 'Opening…' : 'Complete Stripe onboarding'}
                </button>
              )}
            </div>
            </div>
          </div>

          {/* Stripe Payouts Link */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h2 className="text-xl font-semibold text-gray-700 mb-2">Stripe Payouts</h2>
            <p className="text-gray-600 text-sm mb-3">Access your Stripe Express dashboard to view payouts and account settings.</p>
            <Link
              href="#"
              onClick={async (e) => {
                e.preventDefault();
                try {
                  const resp = await getConnectStatus();
                  setConnectStatus(resp);
                  if (!resp || !(resp.charges_enabled && resp.details_submitted)) {
                    alert('Your Stripe onboarding is not completed yet. Please finish onboarding first.');
                    return;
                  }
                  const dl = await fetchWithAuth('/api/payments/connect/dashboard');
                  if (dl.ok) {
                    const data = await dl.json();
                    window.open(data.dashboard_url, '_blank');
                  } else {
                    const err = await dl.json().catch(() => ({} as any));
                    alert(`Unable to open Stripe dashboard: ${err.detail || dl.statusText}`);
                  }
                } catch {
                  alert('Unable to open Stripe dashboard right now.');
                }
              }}
              className="text-purple-700 hover:underline font-medium"
            >
              Open payouts dashboard →
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Total Bookings</h3>
            <p className="text-3xl font-bold text-purple-700">0</p>
            <p className="text-sm text-gray-500 mt-1">Coming soon</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Rating</h3>
            <p className="text-3xl font-bold text-purple-700">-</p>
            <p className="text-sm text-gray-500 mt-1">Not yet available</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Total Earnings</h3>
            <p className="text-3xl font-bold text-purple-700">$0</p>
            <p className="text-sm text-gray-500 mt-1">Payment integration pending</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Link
            href="/instructor/availability"
            className="block p-6 bg-white rounded-lg border border-gray-200 hover:shadow-md transition-shadow"
            onClick={() => logger.debug('Navigating to availability management')}
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Calendar className="w-6 h-6 text-purple-700" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-700">Manage Availability</h3>
                <p className="text-gray-600 text-sm">Set your weekly schedule and available hours</p>
              </div>
            </div>
          </Link>
          <div className="p-6 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
            <div className="text-center text-gray-500">
              <p className="font-semibold">More features coming soon</p>
              <p className="text-sm mt-1">Booking management, analytics, and more</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6 mb-8">
          <div className="flex justify-between items-start mb-6">
            <h2 className="text-xl font-semibold text-gray-700">Profile Information</h2>
            <button
              onClick={() => {
                logger.debug('Opening edit profile modal');
                setShowEditModal(true);
              }}
              className="flex items-center px-4 py-2.5 bg-purple-700 text-white rounded-lg hover:bg-purple-800 transition-colors"
            >
              <Edit className="h-4 w-4 mr-2" />
              Edit Profile
            </button>
          </div>

          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Bio</h3>
              <p className="text-gray-700">{profile.bio}</p>
            </div>

            <div>
              <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-3">Services & Pricing</h3>
              <div className="space-y-2">
                {profile.services.map((service) => (
                  <div key={service.id} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg border border-gray-100">
                    <div>
                      <span className="font-medium text-gray-700">{service.skill}</span>
                      {service.description && <p className="text-sm text-gray-600 mt-1">{service.description}</p>}
                    </div>
                    <span className="font-bold text-purple-700 text-lg">${service.hourly_rate}/hr</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Areas of Service</h3>
                <p className="text-gray-700">{profile.areas_of_service.join(', ')}</p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Experience</h3>
                <p className="text-gray-700">{profile.years_experience} years</p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-4">
          <button
            onClick={handleViewPublicProfile}
            className="flex items-center px-5 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <ExternalLink className="h-5 w-5 mr-2" />
            View Public Profile
          </button>
          <button
            onClick={() => {
              logger.debug('Opening delete profile modal');
              setShowDeleteModal(true);
            }}
            className="flex items-center px-5 py-2.5 bg-red-50 border border-red-200 text-red-700 rounded-lg hover:bg-red-100 transition-colors"
          >
            <Trash2 className="h-5 w-5 mr-2" />
            Delete Instructor Profile
          </button>
          <button
            onClick={async () => {
              try {
                const res = await fetchWithAuth('/api/payments/connect/instant-payout', { method: 'POST' });
                if (!res.ok) {
                  const err = await res.json().catch(() => ({} as any));
                  alert(`Instant payout failed: ${err.detail || res.statusText}`);
                  return;
                }
                const data = await res.json();
                alert(`Instant payout requested: ${data.payout_id || 'OK'}`);
              } catch (e) {
                alert('Instant payout request error');
              }
            }}
            className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            Request Instant Payout
          </button>
        </div>
      </div>

      {showEditModal && (
        <EditProfileModal isOpen={showEditModal} onClose={() => setShowEditModal(false)} onSuccess={handleProfileUpdate} />
      )}
      {showDeleteModal && (
        <DeleteProfileModal isOpen={showDeleteModal} onClose={() => setShowDeleteModal(false)} onSuccess={handleProfileDelete} />
      )}
    </div>
  );
}

function ChecklistRow({ label, ok, action }: { label: string; ok: boolean; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border border-gray-100 rounded-md px-4 py-3">
      <div className="flex items-center gap-2">
        {ok ? <CheckCircle2 className="w-5 h-5 text-green-600" /> : <XCircle className="w-5 h-5 text-gray-300" />}
        <span className="text-gray-800">{label}</span>
      </div>
      <div>{action}</div>
    </div>
  );
}
