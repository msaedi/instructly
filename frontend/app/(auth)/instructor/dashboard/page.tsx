// frontend/app/(auth)/instructor/dashboard/page.tsx
'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Modal from '@/components/Modal';
import { Calendar, Eye, Trash2, Camera, SquareArrowDownLeft, ListTodo, Clock } from 'lucide-react';
import { ProfilePictureUpload } from '@/components/user/ProfilePictureUpload';
import { useInstructorAvailability } from '@/features/instructor-profile/hooks/useInstructorAvailability';
import { getCurrentWeekRange } from '@/types/common';
import { protectedApi } from '@/features/shared/api/client';
import EditProfileModal from '@/components/modals/EditProfileModal';
import DeleteProfileModal from '@/components/modals/DeleteProfileModal';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus, createStripeIdentitySession, createSignedUpload } from '@/lib/api';
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
  const [bookedMinutes, setBookedMinutes] = useState(0);
  const [hasAnyBookings, setHasAnyBookings] = useState<boolean | null>(null);
  const [hasUpcomingBookings, setHasUpcomingBookings] = useState<boolean | null>(null);
  // TEMP: Force mocked empty/upcoming state for preview
  const FORCE_UPCOMING_MOCK = true;
  const [suggestionChecks, setSuggestionChecks] = useState({
    bio: false,
    refer: false,
    bring: false,
    photos: false,
    elite: false,
  });
  const [showVerifyModal, setShowVerifyModal] = useState(false);
  const [bgUploading, setBgUploading] = useState(false);
  const [bgFileInfo, setBgFileInfo] = useState<{ name: string; size: number } | null>(null);

  const fetchProfile = useCallback(async () => {
    try {
      logger.info('Fetching instructor profile');
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);

      if (response.status === 401) {
        logger.warn('Not authenticated, redirecting to login');
        router.push('/login?redirect=/instructor/dashboard');
        return;
      }

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

  // Weekly range for availability/bookings (Mon–Sun)
  const weekRange = getCurrentWeekRange(1);
  const { data: availability } = useInstructorAvailability(profile?.user_id || '', weekRange.start_date);

  // Helpers to calculate minutes from HH:MM or HH:MM:SS
  const parseTimeToMinutes = useCallback((time: string): number => {
    const parts = (time || '').split(':');
    const h = parseInt(parts[0] || '0', 10);
    const m = parseInt(parts[1] || '0', 10);
    return (Number.isFinite(h) ? h : 0) * 60 + (Number.isFinite(m) ? m : 0);
  }, []);
  const diffMinutes = useCallback((start: string, end: string): number => {
    const s = parseTimeToMinutes(start);
    const e = parseTimeToMinutes(end);
    return Math.max(0, e - s);
  }, [parseTimeToMinutes]);

  // Sum available minutes from weekly availability
  const availableMinutes = useMemo(() => {
    if (!availability || !availability.availability_by_date) return 0;
    let total = 0;
    const dayMap = availability.availability_by_date as Record<string, { available_slots?: Array<{ start_time: string; end_time: string }> }>;
    Object.values(dayMap).forEach((day) => {
      const slots = Array.isArray(day?.available_slots) ? day.available_slots : [];
      slots.forEach((slot) => {
        total += diffMinutes(slot.start_time, slot.end_time);
      });
    });
    return total;
  }, [availability, diffMinutes]);

  // Fetch upcoming bookings for the week and compute booked minutes
  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        const res = await protectedApi.getBookings({ upcoming: true, limit: 100 });
        const items = (res.data?.items || []) as Array<{
          booking_date: string; start_time: string; end_time: string;
        }>;
        const withinWeek = items.filter(
          (b) => b.booking_date >= weekRange.start_date && b.booking_date <= weekRange.end_date
        );
        let mins = 0;
        withinWeek.forEach((b) => { mins += diffMinutes(b.start_time, b.end_time); });
        if (!ignore) setBookedMinutes(mins);
      } catch {
        if (!ignore) setBookedMinutes(0);
      }
    })();
    return () => { ignore = true; };
  }, [weekRange.start_date, weekRange.end_date, profile?.user_id, diffMinutes]);

  const availableHours = Math.round(availableMinutes / 60);
  const bookedHours = Math.round(bookedMinutes / 60);

  // Fetch booking presence (ever and upcoming)
  useEffect(() => {
    (async () => {
      try {
        const all = await protectedApi.getBookings({ limit: 1 });
        setHasAnyBookings((all.data?.items?.length || 0) > 0);
      } catch {
        setHasAnyBookings(false);
      }
      try {
        const up = await protectedApi.getBookings({ upcoming: true, limit: 1 });
        setHasUpcomingBookings((up.data?.items?.length || 0) > 0);
      } catch {
        setHasUpcomingBookings(false);
      }
    })();
  }, []);

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
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#6A0DAD]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen">
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
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
              className="inline-block px-6 py-2.5 bg-[#6A0DAD] text-white rounded-lg hover:bg-[#6A0DAD] transition-colors"
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
            <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header with subtle purple accent */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-3 min-w-0">
              <button
                onClick={handleViewPublicProfile}
                aria-label="View public profile"
                title="View public profile"
                className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6A0DAD] transition-colors"
              >
                <svg className="w-6 h-6 text-[#6A0DAD]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </button>
              <div className="min-w-0">
                <h1 className="text-3xl font-bold text-gray-800">Welcome back, {profile.user?.first_name || 'Instructor'}!</h1>
                <p className="text-gray-600 text-sm">Your profile, schedule, and earnings at a glance</p>
              </div>
        </div>
          <button
            onClick={handleViewPublicProfile}
              title="View your public instructor page"
              className="flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium bg-white border border-purple-200 text-[#6A0DAD] hover:bg-purple-50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6A0DAD] focus-visible:ring-offset-1"
          >
              <Eye className="h-4 w-4" />
              <span className="hidden sm:inline">Public profile</span>
          </button>
          </div>
        </div>

        {/* Snapshot Cards directly under header */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Bookings</h3>
            <p className="text-3xl font-bold text-[#6A0DAD]">0</p>
            <p className="text-sm text-gray-500 mt-1">Coming soon</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Rating</h3>
            <p className="text-3xl font-bold text-[#6A0DAD]">-</p>
            <p className="text-sm text-gray-500 mt-1">Not yet available</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Earnings</h3>
            <p className="text-3xl font-bold text-[#6A0DAD]">$0</p>
            <p className="text-sm text-gray-500 mt-1">Payment integration pending</p>
          </div>
        </div>



        {/* Quick Actions (removed; Delete Profile moved into Profile card) */}

        <div className="mb-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Stripe Status Card */}
          <div id="payments-setup" className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-start gap-3">
                <button
                  type="button"
                  onClick={async () => { try { const s = await getConnectStatus(); setConnectStatus(s); } catch {} }}
                  title="Refresh status"
                  aria-label="Refresh status"
                  className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none focus:ring-2 focus:ring-purple-300 transition shrink-0"
                >
                  <SquareArrowDownLeft className="w-6 h-6 text-[#6A0DAD]" />
                </button>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">Payments Setup</h2>
                  <p className="text-gray-600 text-xs mt-0.5">Manage your payouts securely</p>
                  <p className="text-gray-500 text-[11px]">Powered by Stripe</p>
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
                        <svg className="w-4 h-4 text-[#6A0DAD]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Payments enabled</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${detailsSubmitted ? 'text-gray-700' : 'text-gray-500'}`}>
                      {detailsSubmitted ? (
                        <svg className="w-4 h-4 text-[#6A0DAD]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Bank details verified</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${payoutsEnabled ? 'text-gray-700' : 'text-gray-500'}`}>
                      {payoutsEnabled ? (
                        <svg className="w-4 h-4 text-[#6A0DAD]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Payouts active</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${onboardingCompleted ? 'text-gray-700' : 'text-gray-500'}`}>
                      {onboardingCompleted ? (
                        <svg className="w-4 h-4 text-[#6A0DAD]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Setup complete</span>
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
                  className="inline-flex items-center px-3 py-2 text-sm rounded-lg border border-purple-200 bg-purple-50 text-[#6A0DAD] hover:bg-purple-100 disabled:opacity-60"
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
                    className="inline-flex items-center px-4 py-2 text-base rounded-lg border border-purple-200 bg-purple-50 text-[#6A0DAD] hover:bg-purple-100 transition-colors"
                  >
                    View Payouts
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
                    Request Instant Payout
                  </button>
                </div>
          </div>
        </div>
          </div>

          {/* Manage Availability card (only icon is clickable) */}
          <div className="p-6 bg-white rounded-lg border border-gray-200 hover:shadow-md transition-shadow">
            <div className="flex items-start gap-4 w-full">
              <Link
                href="/instructor/availability"
                onClick={() => logger.debug('Navigating to availability management')}
                aria-label="Manage Availability"
                className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] shrink-0"
              >
                <Calendar className="w-6 h-6 text-[#6A0DAD]" />
              </Link>
              <div>
                <h3 className="text-lg font-semibold text-gray-700">Availability</h3>
                <p className="text-gray-600 text-sm">Set your weekly schedule and available hours</p>
              </div>
            </div>
            <div className="mt-10 flex items-center gap-12 justify-center">
              <div className="flex flex-col items-center">
                <div className="w-28 h-28 rounded-full bg-purple-50 border border-purple-200 text-[#6A0DAD] flex items-center justify-center text-2xl font-bold" title="Available hours this week">
                  {availableHours}h
                </div>
                <span className="mt-2 text-sm text-gray-600">Available</span>
              </div>
              <div className="flex flex-col items-center">
                <div className="w-28 h-28 rounded-full bg-gray-50 border border-gray-200 text-gray-700 flex items-center justify-center text-2xl font-bold" title="Booked hours this week">
                  {bookedHours}h
                </div>
                <span className="mt-2 text-sm text-gray-600">Booked</span>
              </div>
          </div>
          </div>
        </div>



        {/* Tasks & Upcoming */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Tasks checklist */}
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <ListTodo className="w-6 h-6 text-[#6A0DAD]" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-800">Action items</h3>
                <p className="text-xs text-black mt-0.5"><span className="text-[#FFD700] font-bold mr-1">*</span>Required to go live</p>
              </div>
            </div>
            <ul className="space-y-2">
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50"
                role="button"
                tabIndex={0}
                onClick={() => { const el = document.getElementById('profile-photo-upload'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { const el = document.getElementById('profile-photo-upload'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } } }}
              >
                <span className="text-gray-700">Upload a profile photo</span>
                <span aria-hidden="true" className="text-[#FFD700] font-extrabold text-3xl leading-none inline-flex items-center justify-center self-center relative top-[1px]">*</span>
              </li>

              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50"
                role="button"
                tabIndex={0}
                onClick={() => { setEditVariant('areas'); setShowEditModal(true); }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { setEditVariant('areas'); setShowEditModal(true); } }}
              >
                <span className="text-gray-700">Set your service area (where you can teach)</span>
                <span aria-hidden="true" className="text-[#FFD700] font-extrabold text-3xl leading-none inline-flex items-center justify-center self-center relative top-[1px]">*</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50"
                role="button"
                tabIndex={0}
                onClick={() => { setEditVariant('services'); setShowEditModal(true); }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { setEditVariant('services'); setShowEditModal(true); } }}
              >
                <span className="text-gray-700">Set your skills</span>
                <span aria-hidden="true" className="text-[#FFD700] font-extrabold text-3xl leading-none inline-flex items-center justify-center self-center relative top-[1px]">*</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50"
                role="button"
                tabIndex={0}
                onClick={() => setShowVerifyModal(true)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setShowVerifyModal(true); }}
              >
                <span className="text-gray-700">Verify your identity</span>
                <span aria-hidden="true" className="text-[#FFD700] font-extrabold text-3xl leading-none inline-flex items-center justify-center self-center relative top-[1px]">*</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50"
                role="button"
                tabIndex={0}
                onClick={() => { const el = document.getElementById('payments-setup'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { const el = document.getElementById('payments-setup'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } } }}
              >
                <span className="text-gray-700">Set payment details (so you can get paid)</span>
                <span aria-hidden="true" className="text-[#FFD700] font-extrabold text-3xl leading-none inline-flex items-center justify-center self-center relative top-[1px]">*</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50"
                role="button"
                tabIndex={0}
                onClick={() => router.push('/instructor/availability')}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') router.push('/instructor/availability'); }}
              >
                <span className="text-gray-700">Set your availability</span>
                <span aria-hidden="true" className="text-[#FFD700] font-extrabold text-3xl leading-none inline-flex items-center justify-center self-center relative top-[1px]">*</span>
              </li>
            </ul>
          </div>
          {/* Upcoming lessons list (placeholder) */}
          <div className="bg-white rounded-lg border border-gray-200 p-6 h-full flex flex-col min-h-[26rem]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Clock className="w-6 h-6 text-[#6A0DAD]" />
                </div>
                <h3 className="text-lg font-semibold text-gray-800">{(FORCE_UPCOMING_MOCK || hasAnyBookings === false) ? 'Let\'s get your first booking' : 'Upcoming lessons'}</h3>
              </div>
              <Link href="/instructor/bookings" className="text-[#6A0DAD] hover:underline text-sm">View all</Link>
            </div>
            {/* Removed small header loader */}
            {(FORCE_UPCOMING_MOCK || hasAnyBookings === false) ? (
              <div className="flex-1 flex items-center justify-center">
                <div className="flex items-center gap-3">
                  <span className="w-3 h-3 rounded-full bg-gray-300 animate-pulse" style={{ animationDelay: '0ms' }} />
                  <span className="w-3 h-3 rounded-full bg-gray-300 animate-pulse" style={{ animationDelay: '200ms' }} />
                  <span className="w-3 h-3 rounded-full bg-gray-300 animate-pulse" style={{ animationDelay: '400ms' }} />
                </div>
              </div>
            ) : (
              <div className="flex-1"></div>
            )}
            <div className="rounded-lg bg-white pr-4 pl-0 py-4">
              {(FORCE_UPCOMING_MOCK || hasUpcomingBookings === false) && (
                <>
                  <div className="h-px bg-gray-200 mb-3"></div>
                  <p className="text-sm text-gray-800 font-medium">No upcoming lessons scheduled</p>
                  <p className="text-xs text-gray-600 mb-3">Here&apos;s how to fill your calendar</p>
                </>
              )}
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.bio}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, bio: !p.bio }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.bio ? 'bg-[#6A0DAD] border-[#6A0DAD] text-white hover:!bg-[#6A0DAD] hover:!border-[#6A0DAD]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
                    title="Mark as done"
                  >
                    {suggestionChecks.bio && (
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF">
                        <path strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setEditVariant('about'); setShowEditModal(true); }}
                    className={`${suggestionChecks.bio ? 'text-[#6A0DAD]' : 'text-gray-700'} hover:underline`}
                  >
                    Polish your profile bio
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.refer}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, refer: !p.refer }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.refer ? 'bg-[#6A0DAD] border-[#6A0DAD] text-white hover:!bg-[#6A0DAD] hover:!border-[#6A0DAD]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
                    title="Mark as done"
                  >
                    {suggestionChecks.refer && (
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF">
                        <path strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => router.push('/instructor/join')}
                    className={`${suggestionChecks.refer ? 'text-[#6A0DAD]' : 'text-gray-700'} hover:underline`}
                  >
                    Refer your colleagues
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.bring}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, bring: !p.bring }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.bring ? 'bg-[#6A0DAD] border-[#6A0DAD] text-white hover:!bg-[#6A0DAD] hover:!border-[#6A0DAD]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
                    title="Mark as done"
                  >
                    {suggestionChecks.bring && (
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF">
                        <path strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => { if (profile?.user_id) window.open(`/instructors/${profile.user_id}`, '_blank'); }}
                    className={`${suggestionChecks.bring ? 'text-[#6A0DAD]' : 'text-gray-700'} hover:underline`}
                  >
                    Bring your students
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.photos}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, photos: !p.photos }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.photos ? 'bg-[#6A0DAD] border-[#6A0DAD] text-white hover:!bg-[#6A0DAD] hover:!border-[#6A0DAD]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
                    title="Mark as done"
                  >
                    {suggestionChecks.photos && (
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF">
                        <path strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => router.push('/instructor/profile')}
                    className={`${suggestionChecks.photos ? 'text-[#6A0DAD]' : 'text-gray-700'} hover:underline`}
                  >
                    Add related skill pictures
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.elite}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, elite: !p.elite }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.elite ? 'bg-[#6A0DAD] border-[#6A0DAD] text-white hover:!bg-[#6A0DAD] hover:!border-[#6A0DAD]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
                    title="Mark as done"
                  >
                    {suggestionChecks.elite && (
                      <svg className="w-2 h-2" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF">
                        <path strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => router.push('/instructor/welcome')}
                    className={`${suggestionChecks.elite ? 'text-[#6A0DAD]' : 'text-gray-700'} hover:underline`}
                  >
                    Earn Elite status
                  </button>
                </li>
              </ul>
            </div>
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
                      <div id="profile-photo-upload" className="w-20 h-20 rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 focus:outline-none cursor-pointer" title="Upload profile photo">
                        <Camera className="w-6 h-6 text-[#6A0DAD]" />
                      </div>
                    }
                  />
                  <h3 className="text-base font-semibold text-gray-800">About You</h3>
                </div>
                <button onClick={() => { setEditVariant('about'); setShowEditModal(true); }} className="text-[#6A0DAD] hover:underline text-sm">Edit</button>
              </div>
              <p className="text-gray-600 text-xs">Experience: {profile.years_experience} years</p>
              <p className="text-gray-700 text-sm mt-2">{profile.bio}</p>
            </div>

            <div className="rounded-lg border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-800">Skills & Pricing</h3>
                <button onClick={() => { setEditVariant('services'); setShowEditModal(true); }} className="text-[#6A0DAD] hover:underline text-sm">Edit</button>
              </div>
              <div className="space-y-2">
                {profile.services.map((service) => (
                  <div key={service.id} className="flex justify-between items-center p-3 bg-white rounded-lg border border-gray-100">
                    <div>
                      <span className="font-medium text-gray-700">{service.skill}</span>
                      {service.description && <p className="text-sm text-gray-600 mt-1">{service.description}</p>}
                    </div>
                    <span className="font-bold text-[#6A0DAD] text-lg">${service.hourly_rate}/hr</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-800">Service Areas</h3>
                <button onClick={() => { setEditVariant('areas'); setShowEditModal(true); }} className="text-[#6A0DAD] hover:underline text-sm">Edit</button>
              </div>
              {(() => {
                const areas = (serviceAreaNames && serviceAreaNames.length > 0)
                  ? serviceAreaNames
                  : (profile.areas_of_service || []);
                return areas && areas.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {areas.map((area) => (
                      <span key={area} className="px-2 py-1 text-xs rounded-full bg-purple-50 text-[#6A0DAD] border border-purple-200">{area}</span>
                    ))}
              </div>
                ) : (
                  <p className="text-gray-500 text-sm">No service areas selected.</p>
                );
              })()}
            </div>


          </div>
          <div className="mt-6 flex justify-end">
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
      <Modal isOpen={showVerifyModal} onClose={() => setShowVerifyModal(false)} title="Verify your identity" size="xl">
        {/* Inline minimal content from verification page */}
        <div className="space-y-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
              <svg className="w-5 h-5 text-[#6A0DAD]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Identity Verification</h2>
              <p className="text-gray-600 mt-1">Verify your identity with a government ID and selfie</p>
            </div>
          </div>
          <div className="flex items-center gap-6 text-sm text-gray-500">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>~5 minutes</span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              <span>Secure & encrypted</span>
            </div>
          </div>
          <div>
            <button
              onClick={async () => {
                try {
                  setShowVerifyModal(false);
                  const session = await createStripeIdentitySession();
                  try {
                    const pk = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
                    if (pk) {
                      const stripe = await (await import('@stripe/stripe-js')).loadStripe(pk);
                      if (stripe) {
                        const result = await stripe.verifyIdentity(session.client_secret);
                        if (result && typeof (result as { error?: unknown }).error === 'undefined') return;
                      }
                    }
                  } catch {}
                  window.location.href = `https://verify.stripe.com/start/${session.client_secret}`;
                } catch {}
              }}
              className="inline-flex items-center px-5 py-2.5 rounded-lg text-white bg-[#6A0DAD] hover:bg-[#6A0DAD] transition-colors font-medium"
            >
              Start Verification
            </button>
          </div>

          {/* Divider */}
          <div className="h-px bg-gray-200 my-2"></div>

          {/* Background Check (from verification page) */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-[#6A0DAD]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div className="flex-1">
                <h2 className="text-base font-semibold text-gray-900">Background Check</h2>
                <p className="text-gray-600 mt-1 text-sm">Upload your background check document (optional)</p>

                <div className="mt-3 p-3 bg-purple-50 rounded-lg border border-purple-100">
                  <p className="text-sm text-purple-900 font-medium mb-2">Accepted providers:</p>
                  <div className="flex flex-wrap gap-2">
                    <span className="inline-flex items-center px-2.5 py-1 bg-white rounded-md text-xs text-[#6A0DAD] border border-purple-200">Checkr</span>
                    <span className="inline-flex items-center px-2.5 py-1 bg-white rounded-md text-xs text-[#6A0DAD] border border-purple-200">Sterling</span>
                    <span className="inline-flex items-center px-2.5 py-1 bg-white rounded-md text-xs text-[#6A0DAD] border border-purple-200">NYC DOE</span>
                  </div>
                </div>

                <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
                  <span>PDF, JPG, PNG</span>
                  <span>•</span>
                  <span>Max 10MB</span>
                </div>

                <div className="mt-4">
                  <label className="inline-flex items-center px-4 py-2.5 rounded-lg bg-purple-50 border border-purple-200 text-[#6A0DAD] font-medium hover:bg-purple-100 transition-colors cursor-pointer">
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      className="hidden"
                      onChange={async (e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        try {
                          setBgUploading(true);
                          const signed = await createSignedUpload({
                            filename: f.name,
                            content_type: f.type || 'application/octet-stream',
                            size_bytes: f.size,
                            purpose: 'background_check',
                          });
                          const putRes = await fetch(signed.upload_url, {
                            method: 'PUT',
                            headers: signed.headers,
                            body: f,
                          });
                          if (!putRes.ok) throw new Error('Upload failed');
                          setBgFileInfo({ name: f.name, size: f.size });
                        } catch (err) {
                          logger.error('Background check upload failed', err);
                          alert('Upload failed');
                        } finally {
                          setBgUploading(false);
                        }
                      }}
                      disabled={bgUploading}
                    />
                    <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <span>{bgUploading ? 'Uploading…' : 'Choose File'}</span>
                  </label>
                  {bgFileInfo && (
                    <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                      </svg>
                      <span>{bgFileInfo.name}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Modal>
      {showDeleteModal && (
        <DeleteProfileModal isOpen={showDeleteModal} onClose={() => setShowDeleteModal(false)} onSuccess={handleProfileDelete} />
      )}
    </div>
  );
}
