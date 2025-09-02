// frontend/app/(auth)/instructor/dashboard/page.tsx
'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Calendar, ExternalLink, Trash2, RefreshCcw, Camera } from 'lucide-react';
import { ProfilePictureUpload } from '@/components/user/ProfilePictureUpload';
import EditProfileModal from '@/components/modals/EditProfileModal';
import DeleteProfileModal from '@/components/modals/DeleteProfileModal';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { logger } from '@/lib/logger';
import { InstructorProfile } from '@/types/instructor';
import { useAuth } from '@/features/shared/hooks/useAuth';
import UserProfileDropdown from '@/components/UserProfileDropdown';

export default function InstructorDashboardNew() {
  const router = useRouter();
  const { logout } = useAuth();
  const [profile, setProfile] = useState<InstructorProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editVariant, setEditVariant] = useState<'full' | 'about' | 'areas' | 'services'>('full');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [connectStatus, setConnectStatus] = useState<{
    charges_enabled?: boolean;
    payouts_enabled?: boolean;
    details_submitted?: boolean;
  } | null>(null);

  const [isStartingStripeOnboarding, setIsStartingStripeOnboarding] = useState(false);
  const [serviceAreaNames, setServiceAreaNames] = useState<string[] | null>(null);

  const fetchProfile = useCallback(async () => {
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
      // Fetch canonical service areas (exact neighborhoods)
      try {
        const areasRes = await fetchWithAuth('/api/addresses/service-areas/me');
        if (areasRes.ok) {
          const areasJson = await areasRes.json();
          const items = (areasJson.items || []) as Array<{ name?: string | null }>;
          const names = Array.from(new Set(items.map((i) => (i.name || '').trim()).filter(Boolean)));
          setServiceAreaNames(names);
        } else {
          setServiceAreaNames(null);
        }
      } catch {
        setServiceAreaNames(null);
      }
    } catch (err) {
      logger.error('Error fetching instructor profile', err);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  useEffect(() => {
    logger.info('Instructor dashboard (new) loaded');
    fetchProfile();
    (async () => {
      try {
        const s = await getConnectStatus();
        setConnectStatus(s);
      } catch {
        logger.warn('Failed to load connect status');
      }
    })();
  }, [router, fetchProfile]);

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
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
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



  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header with subtle purple accent */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
              <svg className="w-6 h-6 text-purple-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-3xl font-bold text-gray-800">Welcome back, {profile.user?.first_name || 'Instructor'}!</h1>
              <p className="text-gray-600 text-sm">Your profile, schedule, and earnings at a glance</p>
            </div>

          </div>
        </div>

        {/* Snapshot Cards directly under header */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Bookings</h3>
            <p className="text-3xl font-bold text-purple-700">0</p>
            <p className="text-sm text-gray-500 mt-1">Coming soon</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Rating</h3>
            <p className="text-3xl font-bold text-purple-700">-</p>
            <p className="text-sm text-gray-500 mt-1">Not yet available</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Earnings</h3>
            <p className="text-3xl font-bold text-purple-700">$0</p>
            <p className="text-sm text-gray-500 mt-1">Payment integration pending</p>
          </div>
        </div>



        {/* Quick Actions */}
        <div className="mb-6 flex flex-wrap gap-4">
          <button
            onClick={handleViewPublicProfile}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-purple-50 border border-purple-200 text-purple-700 hover:bg-purple-100 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            <span>View Public Profile</span>
          </button>
          <button
            onClick={() => {
              logger.debug('Opening delete profile modal');
              setShowDeleteModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-red-50 border border-red-200 text-red-700 hover:bg-red-100 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
            <span>Delete Profile</span>
          </button>
        </div>

        <div className="mb-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Stripe Status Card */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={async () => { try { const s = await getConnectStatus(); setConnectStatus(s); } catch {} }}
                  title="Refresh status"
                  aria-label="Refresh status"
                  className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none focus:ring-2 focus:ring-purple-300 transition"
                >
                  <RefreshCcw className="w-6 h-6 text-purple-700" />
                </button>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Stripe Account</h2>
                  <p className="text-gray-600 text-xs mt-0.5">Manage onboarding and payouts</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2.5 py-1 rounded-md border ${connectStatus && connectStatus.charges_enabled && connectStatus.details_submitted ? 'bg-green-50 text-green-700 border-green-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                  {connectStatus && connectStatus.charges_enabled && connectStatus.details_submitted ? 'Connected' : 'Action required'}
                </span>
              </div>
            </div>
              <p className="text-gray-600 text-sm mb-4">Your Stripe account setup status.</p>
            {connectStatus ? (() => {
              const chargesEnabled = Boolean(connectStatus?.charges_enabled);
              const payoutsEnabled = Boolean(connectStatus?.payouts_enabled);
              const detailsSubmitted = Boolean(connectStatus?.details_submitted);
              // Compute UI completion from live signals rather than trusting stale flag
              const onboardingCompleted = Boolean(chargesEnabled && detailsSubmitted);
              const allGood = chargesEnabled && payoutsEnabled && detailsSubmitted && onboardingCompleted;
              return (
                <div>
                  <ul className="grid grid-cols-2 gap-2">
                    <li className={`flex items-center gap-2 text-sm ${chargesEnabled ? 'text-gray-700' : 'text-gray-500'}`}>
                      {chargesEnabled ? (
                        <svg className="w-4 h-4 text-purple-700" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Charges enabled</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${payoutsEnabled ? 'text-gray-700' : 'text-gray-500'}`}>
                      {payoutsEnabled ? (
                        <svg className="w-4 h-4 text-purple-700" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Payouts enabled</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${detailsSubmitted ? 'text-gray-700' : 'text-gray-500'}`}>
                      {detailsSubmitted ? (
                        <svg className="w-4 h-4 text-purple-700" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Details verified</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${onboardingCompleted ? 'text-gray-700' : 'text-gray-500'}`}>
                      {onboardingCompleted ? (
                        <svg className="w-4 h-4 text-purple-700" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Onboarding completed</span>
                    </li>
                  </ul>
                  {!allGood && (
                    <div className="mt-3 text-xs text-gray-600">Finish Stripe setup to start receiving payouts.</div>
                  )}
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
                    } catch {
                      alert('Unable to start Stripe onboarding right now.');
                    } finally {
                      setIsStartingStripeOnboarding(false);
                    }
                  }}
                  disabled={isStartingStripeOnboarding}
                  className="inline-flex items-center px-3 py-2 text-sm rounded-lg border border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100 disabled:opacity-60"
                >
                  {isStartingStripeOnboarding ? 'Opening…' : 'Complete Stripe onboarding'}
                </button>
              )}
              {/* Payouts and Instant Payout */}
              <div className="mt-6 border-t border-gray-200 pt-4">
                <h3 className="text-sm font-medium text-gray-700 mb-1">Stripe Payouts</h3>
                <p className="text-gray-600 text-xs mb-2">Access your Stripe Express dashboard to view payouts and account settings.</p>
                <div className="flex items-center gap-3 flex-wrap justify-end">
                  <button
                    onClick={async () => {
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
                          const err = await dl.json().catch(() => ({ detail: 'Unknown error' }));
                          alert(`Unable to open Stripe dashboard: ${err.detail || dl.statusText}`);
                        }
                      } catch {
                        alert('Unable to open Stripe dashboard right now.');
                      }
                    }}
                    className="inline-flex items-center px-4 py-2 text-base rounded-lg border border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100 transition-colors"
                  >
                    Payouts Dashboard
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const res = await fetchWithAuth('/api/payments/connect/instant-payout', { method: 'POST' });
                        if (!res.ok) {
                          const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
                          alert(`Instant payout failed: ${err.detail || res.statusText}`);
                          return;
                        }
                        const data = await res.json();
                        alert(`Instant payout requested: ${data.payout_id || 'OK'}`);
                      } catch {
                        alert('Instant payout request error');
                      }
                    }}
                    className="inline-flex items-center px-4 py-2 text-base rounded-lg bg-[#6A0DAD] text-white hover:bg-[#5c0a9a] transition-colors"
                  >
                    Instant payout request
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Manage Availability card (only icon is clickable) */}
          <div className="p-6 bg-white rounded-lg border border-gray-200 hover:shadow-md transition-shadow">
            <div className="flex items-center gap-4">
              <Link
                href="/instructor/availability"
                onClick={() => logger.debug('Navigating to availability management')}
                aria-label="Manage Availability"
                className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
              >
                <Calendar className="w-6 h-6 text-purple-700" />
              </Link>
              <div>
                <h3 className="text-lg font-semibold text-gray-700">Manage Availability</h3>
                <p className="text-gray-600 text-sm">Set your weekly schedule and available hours</p>
              </div>
            </div>
          </div>
        </div>



        {/* Tasks & Upcoming */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Tasks checklist */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-lg font-semibold text-gray-800 mb-3">Tasks to complete</h3>
            <ul className="space-y-2">
              <li className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2">
                <span className="text-gray-700">Add availability for this week</span>
                <Link href="/instructor/availability" className="text-purple-700 hover:underline text-sm">Open</Link>
              </li>
              <li className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2">
                <span className="text-gray-700">Finish Stripe onboarding</span>
                <Link href="/instructor/onboarding/status" className="text-purple-700 hover:underline text-sm">Continue</Link>
              </li>
              <li className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2">
                <span className="text-gray-700">Polish your public profile bio</span>
                <button onClick={() => setShowEditModal(true)} className="text-purple-700 hover:underline text-sm">Edit</button>
              </li>
            </ul>
          </div>
          {/* Upcoming lessons list (placeholder) */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-gray-800">Upcoming lessons</h3>
              <Link href="/instructor/bookings" className="text-purple-700 hover:underline text-sm">View all</Link>
            </div>
            <div className="text-gray-500 text-sm">No upcoming lessons scheduled.</div>
          </div>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6 mb-8">
          <div className="flex justify-between items-start mb-6">
            <h2 className="text-xl font-semibold text-gray-700">Profile Information</h2>
          </div>

          <div className="space-y-6">
            <div className="rounded-lg border border-gray-200 p-5">
              <div className="flex items-start justify-between mb-3">
                <div className="flex flex-col items-start gap-2">
                  <ProfilePictureUpload
                    ariaLabel="Upload profile photo"
                    trigger={
                      <div className="w-20 h-20 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none cursor-pointer" title="Upload profile photo">
                        <Camera className="w-6 h-6 text-purple-700" />
                      </div>
                    }
                  />
                  <h3 className="text-base font-semibold text-gray-800">About You</h3>
                </div>
                <button onClick={() => { setEditVariant('about'); setShowEditModal(true); }} className="text-purple-700 hover:underline text-sm">Edit</button>
              </div>
              <p className="text-gray-600 text-xs">Experience: {profile.years_experience} years</p>
              <p className="text-gray-700 text-sm mt-2">{profile.bio}</p>
            </div>

            <div className="rounded-lg border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-800">Skills & Pricing</h3>
                <button onClick={() => { setEditVariant('services'); setShowEditModal(true); }} className="text-purple-700 hover:underline text-sm">Edit</button>
              </div>
              <div className="space-y-2">
                {profile.services.map((service) => (
                  <div key={service.id} className="flex justify-between items-center p-3 bg-white rounded-lg border border-gray-100">
                    <div>
                      <span className="font-medium text-gray-700">{service.skill}</span>
                      {service.description && <p className="text-sm text-gray-600 mt-1">{service.description}</p>}
                    </div>
                    <span className="font-bold text-purple-700 text-lg">${service.hourly_rate}/hr</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-800">Service Areas</h3>
                <button onClick={() => { setEditVariant('areas'); setShowEditModal(true); }} className="text-purple-700 hover:underline text-sm">Edit</button>
              </div>
              {(() => {
                const areas = (serviceAreaNames && serviceAreaNames.length > 0)
                  ? serviceAreaNames
                  : (profile.areas_of_service || []);
                return areas && areas.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {areas.map((area) => (
                      <span key={area} className="px-2 py-1 text-xs rounded-full bg-purple-50 text-purple-700 border border-purple-200">{area}</span>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">No service areas selected.</p>
                );
              })()}
            </div>


          </div>
        </div>


      </div>

      {showEditModal && (
        <EditProfileModal
          isOpen={showEditModal}
          onClose={() => setShowEditModal(false)}
          onSuccess={handleProfileUpdate}
          variant={editVariant}
        />
      )}
      {showDeleteModal && (
        <DeleteProfileModal isOpen={showDeleteModal} onClose={() => setShowDeleteModal(false)} onSuccess={handleProfileDelete} />
      )}
    </div>
  );
}
