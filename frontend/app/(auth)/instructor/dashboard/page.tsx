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
import { normalizeInstructorServices, hydrateCatalogNameById, displayServiceName } from '@/lib/instructorServices';
import { getServiceAreaBoroughs } from '@/lib/profileServiceAreas';
import { httpPut } from '@/features/shared/api/http';

type NeighborhoodSelection = { neighborhood_id: string; name: string };
type PreferredTeachingLocation = { address: string; label?: string };
type PreferredPublicSpace = { address: string };

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
  const [isRefreshingConnect, setIsRefreshingConnect] = useState(false);
  const [serviceAreaNames, setServiceAreaNames] = useState<string[] | null>(null);
  const [serviceAreaSelections, setServiceAreaSelections] = useState<NeighborhoodSelection[]>([]);
  const [preferredTeachingLocations, setPreferredTeachingLocations] = useState<PreferredTeachingLocation[]>([]);
  const [preferredPublicSpaces, setPreferredPublicSpaces] = useState<PreferredPublicSpace[]>([]);
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

      const profileRecord = data as unknown as Record<string, unknown>;
      const teachingFromApi = Array.isArray(profileRecord['preferred_teaching_locations'])
        ? (profileRecord['preferred_teaching_locations'] as Array<Record<string, unknown>>)
        : [];
      const nextTeaching: PreferredTeachingLocation[] = [];
      const teachingSeen = new Set<string>();
      for (const entry of teachingFromApi) {
        const rawAddress = typeof entry?.['address'] === 'string' ? entry['address'].trim() : '';
        if (!rawAddress) continue;
        const key = rawAddress.toLowerCase();
        if (teachingSeen.has(key)) continue;
        teachingSeen.add(key);
        const rawLabel = typeof entry?.['label'] === 'string' ? entry['label'].trim() : '';
        nextTeaching.push(rawLabel ? { address: rawAddress, label: rawLabel } : { address: rawAddress });
        if (nextTeaching.length === 2) break;
      }
      setPreferredTeachingLocations(nextTeaching);

      const publicFromApi = Array.isArray(profileRecord['preferred_public_spaces'])
        ? (profileRecord['preferred_public_spaces'] as Array<Record<string, unknown>>)
        : [];
      const nextPublic: PreferredPublicSpace[] = [];
      const publicSeen = new Set<string>();
      for (const entry of publicFromApi) {
        const rawAddress = typeof entry?.['address'] === 'string' ? entry['address'].trim() : '';
        if (!rawAddress) continue;
        const key = rawAddress.toLowerCase();
        if (publicSeen.has(key)) continue;
        publicSeen.add(key);
        nextPublic.push({ address: rawAddress });
        if (nextPublic.length === 2) break;
      }
      setPreferredPublicSpaces(nextPublic);

      const serviceAreaBoroughs = getServiceAreaBoroughs(data);

      logger.info('Instructor profile loaded successfully', {
        userId: data.user_id,
        servicesCount: data.services.length,
        boroughCount: serviceAreaBoroughs.length,
      });

      const normalizedServices = await normalizeInstructorServices(data.services);
      setProfile({ ...data, services: normalizedServices });
      // Fetch canonical service areas (exact neighborhoods)
      try {
        const areasRes = await fetchWithAuth('/api/addresses/service-areas/me');
        if (areasRes.ok) {
          const areasJson = await areasRes.json();
          const items = (areasJson.items || []) as Array<Record<string, unknown>>;
          const selectionMap = new Map<string, NeighborhoodSelection>();
          for (const item of items) {
            const rawId = item?.['neighborhood_id'] ?? item?.['id'];
            if (typeof rawId !== 'string' && typeof rawId !== 'number') continue;
            const id = String(rawId);
            const rawName = typeof item?.['name'] === 'string' ? (item['name'] as string).trim() : '';
            selectionMap.set(id, { neighborhood_id: id, name: rawName || id });
          }
          const selections = Array.from(selectionMap.values());
          setServiceAreaSelections(selections);
          const names = selections.map((selection) => selection.name).filter((name) => name.length > 0);
          setServiceAreaNames(names.length > 0 ? names : null);
        } else {
          setServiceAreaNames(null);
          setServiceAreaSelections([]);
        }
      } catch {
        setServiceAreaNames(null);
        setServiceAreaSelections([]);
      }
    } catch (err) {
      logger.error('Error fetching instructor profile', err);
      setPreferredTeachingLocations([]);
      setPreferredPublicSpaces([]);
      setServiceAreaSelections([]);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  useEffect(() => {
    logger.info('Instructor dashboard (new) loaded');
    void fetchProfile();
    void (async () => {
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
    void fetchProfile();
    setShowEditModal(false);
  };

  const handleAreasModalSave = useCallback(async (payload: {
    neighborhoods: NeighborhoodSelection[];
    preferredTeaching: PreferredTeachingLocation[];
    preferredPublic: PreferredPublicSpace[];
  }) => {
    try {
      const neighborhoodIds = payload.neighborhoods.map((item) => item.neighborhood_id);
      await httpPut('/api/addresses/service-areas/me', { neighborhood_ids: neighborhoodIds });
      await httpPut('/instructors/me', {
        preferred_teaching_locations: payload.preferredTeaching,
        preferred_public_spaces: payload.preferredPublic,
      });
      setServiceAreaSelections(payload.neighborhoods);
      setPreferredTeachingLocations(payload.preferredTeaching);
      setPreferredPublicSpaces(payload.preferredPublic);
      const names = payload.neighborhoods.map((item) => item.name).filter((name) => name.length > 0);
      setServiceAreaNames(names.length > 0 ? names : null);
    } catch (err) {
      logger.error('Failed to save service areas from dashboard', err);
      throw err;
    }
  }, []);

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
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#7E22CE]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen">
        <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
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
              className="inline-block px-6 py-2.5 bg-[#7E22CE] text-white rounded-lg"
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
      <header className="bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-0 sm:pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header with subtle purple accent */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-3 min-w-0">
              <div
                aria-hidden="true"
                className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center select-none"
              >
                <svg className="w-6 h-6 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <div className="min-w-0">
                <h1 className="text-3xl font-bold text-gray-800 mb-2">Welcome back, {profile.user?.first_name || 'Instructor'}!</h1>
                <p className="text-gray-600 text-sm">Your profile, schedule, and earnings at a glance</p>
              </div>
        </div>
          {(() => {
            const releaseTs = Date.UTC(2025, 11, 1, 0, 0, 0); // Dec 1, 2025 (UTC)
            const isEnabled = Date.now() >= releaseTs;
            return (
              <button
                onClick={handleViewPublicProfile}
                disabled={!isEnabled}
                aria-disabled={!isEnabled}
                title={isEnabled ? 'View your public instructor page' : 'Public profile available Dec 1, 2025'}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium ${
                  isEnabled
                    ? 'bg-white border border-purple-200 text-[#7E22CE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#7E22CE] focus-visible:ring-offset-1'
                    : 'bg-gray-100 border border-gray-300 text-gray-400 cursor-not-allowed'
                }`}
              >
                <Eye className="h-4 w-4" />
                <span className="hidden sm:inline">Public profile</span>
              </button>
            );
          })()}
          </div>
        </div>

        {/* Action items card removed per request */}

        {/* Snapshot Cards directly under header */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Bookings</h3>
            <p className="text-3xl font-bold text-[#7E22CE]">0</p>
            <p className="text-sm text-gray-500 mt-1">Coming soon</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Rating</h3>
            <p className="text-3xl font-bold text-[#7E22CE]">-</p>
            <p className="text-sm text-gray-500 mt-1">Not yet available</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-sm font-medium text-gray-600 uppercase tracking-wide mb-2">Earnings</h3>
            <p className="text-3xl font-bold text-[#7E22CE]">$0</p>
            <p className="text-sm text-gray-500 mt-1">Payment integration pending</p>
          </div>
        </div>



        {/* Quick Actions (removed; Delete Profile moved into Profile card) */}

        <div className="mb-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Stripe Status Card */}
          <div id="payments-setup" className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 h-full flex flex-col relative">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-start gap-3">
                <div className="relative group">
                  <button
                    type="button"
                    onClick={async () => {
                      if (isRefreshingConnect) return;
                      setIsRefreshingConnect(true);
                      try {
                        const s = await getConnectStatus();
                        setConnectStatus(s);
                        try { (await import('sonner')).toast?.info?.('Status refreshed'); } catch {}
                      } catch {
                        try { (await import('sonner')).toast?.error?.('Failed to refresh status'); } catch {}
                      } finally {
                        setIsRefreshingConnect(false);
                      }
                    }}
                    aria-label="Refresh status"
                    aria-busy={isRefreshingConnect}
                    disabled={isRefreshingConnect}
                    aria-describedby="refresh-status-tip"
                  className={`w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-purple-300 transition shrink-0 ${isRefreshingConnect ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-100'}`}
                  >
                    <SquareArrowDownLeft className={`w-6 h-6 text-[#7E22CE] ${isRefreshingConnect ? 'animate-spin' : 'transition-transform duration-150 ease-out group-hover:scale-110'}`} />
                  </button>
                  <div
                    role="tooltip"
                    id="refresh-status-tip"
                    className="pointer-events-none absolute z-50 left-1/2 -translate-x-1/2 top-full mt-2 whitespace-nowrap rounded-md bg-white text-gray-800 text-xs shadow-lg border border-gray-200 px-2 py-1 opacity-0 translate-y-1 group-hover:opacity-100 group-focus-within:opacity-100 group-hover:translate-y-0 group-focus-within:translate-y-0 transition-all duration-150"
                  >
                    Refresh status
                  </div>
                </div>
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
                        <svg className="w-4 h-4 text-[#7E22CE]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Payments enabled</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${detailsSubmitted ? 'text-gray-700' : 'text-gray-500'}`}>
                      {detailsSubmitted ? (
                        <svg className="w-4 h-4 text-[#7E22CE]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Bank details verified</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${payoutsEnabled ? 'text-gray-700' : 'text-gray-500'}`}>
                      {payoutsEnabled ? (
                        <svg className="w-4 h-4 text-[#7E22CE]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Payouts active</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${onboardingCompleted ? 'text-gray-700' : 'text-gray-500'}`}>
                      {onboardingCompleted ? (
                        <svg className="w-4 h-4 text-[#7E22CE]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
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
                      const retPath = '/instructor/dashboard';
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
                  className="inline-flex items-center px-3 py-2 text-sm rounded-lg border border-purple-200 bg-purple-50 text-[#7E22CE] disabled:opacity-60"
                >
                  {isStartingStripeOnboarding ? 'Opening…' : 'Complete Stripe onboarding'}
                </button>
              )}
              {/* Payouts and Instant Payout */}
              <div className="mt-auto border-t border-gray-200 pt-4">
                <h3 className="text-sm font-medium text-gray-700 mb-1">Stripe Payouts</h3>
                <p className="text-gray-600 text-xs mb-2">Access your Stripe Express dashboard to view payouts and account settings.</p>
                <div className="flex flex-wrap items-center gap-3 justify-end">
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
                    className="inline-flex items-center justify-center h-10 px-4 text-base rounded-lg border border-purple-200 bg-purple-50 text-[#7E22CE] w-full sm:w-auto"
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
                    className="inline-flex items-center justify-center h-10 px-4 text-base rounded-lg bg-[#7E22CE] text-white whitespace-nowrap w-full sm:w-auto sm:min-w-[13rem]"
                  >
                    Request Instant Payout
                  </button>
                </div>
          </div>
        </div>
          </div>

          {/* Manage Availability card (only icon is clickable) */}
          <div className="p-6 bg-white rounded-lg border border-gray-200 hover:shadow-md transition-shadow h-full flex flex-col relative">
            <div className="flex items-start gap-4 w-full">
              <Link
                href="/instructor/availability"
                onClick={() => logger.debug('Navigating to availability management')}
                aria-label="Manage Availability"
                className="group relative w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] transition shrink-0 overflow-hidden"
              >
                <span className="absolute inset-0 rounded-full bg-gray-100 opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
                <Calendar className="relative w-6 h-6 text-[#7E22CE] transition-transform duration-150 ease-out group-hover:scale-110" />
              </Link>
              <div>
                <h3 className="text-lg font-semibold text-gray-700">Availability</h3>
                <p className="text-gray-600 text-sm">Set your weekly schedule and available hours</p>
              </div>
            </div>
            <div className="mt-10 flex items-center gap-12 justify-center">
              <div className="flex flex-col items-center">
                <div className="w-28 h-28 rounded-full bg-purple-50 border border-purple-200 text-[#7E22CE] flex items-center justify-center text-2xl font-bold" title="Available hours this week">
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
          <div className="mt-auto border-t border-gray-200 pt-4">
            <div className="flex flex-wrap items-center gap-3 justify-end">
              <Link
                href="/instructor/availability"
                className="inline-flex items-center justify-center h-10 px-4 text-base rounded-lg bg-[#7E22CE] text-white whitespace-nowrap w-full sm:w-auto sm:min-w-[13rem]"
                onClick={() => logger.debug('Open Calendar button clicked')}
              >
                Open Calendar
              </Link>
            </div>
          </div>
          </div>
        </div>



        {/* Tasks & Upcoming */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Tasks checklist */}
          <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm ring-1 ring-purple-100">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <ListTodo className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div>
                <h3 className="text-xl font-bold text-gray-800">Action items</h3>
                <p className="text-xs text-gray-600 mt-0.5">Complete these steps to go live</p>
              </div>
            </div>
            <ul className="space-y-2">
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50 cursor-pointer"
                role="button"
                tabIndex={0}
                onClick={() => { const el = document.getElementById('profile-photo-upload'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { const el = document.getElementById('profile-photo-upload'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } } }}
              >
                <span className="text-gray-700">Upload a profile photo</span>
              </li>

              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50 cursor-pointer"
                role="button"
                tabIndex={0}
                onClick={() => { setEditVariant('areas'); setShowEditModal(true); }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { setEditVariant('areas'); setShowEditModal(true); } }}
              >
                <span className="text-gray-700">Set your service area (where you can teach)</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50 cursor-pointer"
                role="button"
                tabIndex={0}
                onClick={() => { setEditVariant('services'); setShowEditModal(true); }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { setEditVariant('services'); setShowEditModal(true); } }}
              >
                <span className="text-gray-700">Set your skills</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50 cursor-pointer"
                role="button"
                tabIndex={0}
                onClick={() => setShowVerifyModal(true)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setShowVerifyModal(true); }}
              >
                <span className="text-gray-700">Verify your identity</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50 cursor-pointer"
                role="button"
                tabIndex={0}
                onClick={() => { const el = document.getElementById('payments-setup'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } }}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { const el = document.getElementById('payments-setup'); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } } }}
              >
                <span className="text-gray-700">Set payment details (so you can get paid)</span>
              </li>
              <li
                className="flex items-center justify-between border border-gray-100 rounded-md px-3 py-2 clickable hover:bg-gray-50 cursor-pointer"
                role="button"
                tabIndex={0}
                onClick={() => router.push('/instructor/availability')}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') router.push('/instructor/availability'); }}
              >
                <span className="text-gray-700">Set your availability</span>
              </li>
            </ul>
          </div>
          {/* Upcoming lessons list (placeholder) */}
          <div className="bg-white rounded-lg border border-gray-200 p-6 h-full flex flex-col min-h-[26rem]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Clock className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <h3 className="text-lg font-semibold text-gray-800">{(FORCE_UPCOMING_MOCK || hasAnyBookings === false) ? 'Let\'s get your first booking' : 'Upcoming lessons'}</h3>
              </div>
              <Link href="/instructor/bookings" className="text-[#7E22CE] hover:underline text-sm">View all</Link>
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
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.bio ? 'bg-[#7E22CE] border-[#7E22CE] text-white hover:!bg-[#7E22CE] hover:!border-[#7E22CE]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
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
                    className={`${suggestionChecks.bio ? 'text-[#7E22CE]' : 'text-gray-700'} hover:underline`}
                  >
                    Polish your profile bio
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.refer}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, refer: !p.refer }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.refer ? 'bg-[#7E22CE] border-[#7E22CE] text-white hover:!bg-[#7E22CE] hover:!border-[#7E22CE]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
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
                    className={`${suggestionChecks.refer ? 'text-[#7E22CE]' : 'text-gray-700'} hover:underline`}
                  >
                    Refer your colleagues
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.bring}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, bring: !p.bring }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.bring ? 'bg-[#7E22CE] border-[#7E22CE] text-white hover:!bg-[#7E22CE] hover:!border-[#7E22CE]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
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
                    className={`${suggestionChecks.bring ? 'text-[#7E22CE]' : 'text-gray-700'} hover:underline`}
                  >
                    Bring your students
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.photos}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, photos: !p.photos }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.photos ? 'bg-[#7E22CE] border-[#7E22CE] text-white hover:!bg-[#7E22CE] hover:!border-[#7E22CE]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
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
                    className={`${suggestionChecks.photos ? 'text-[#7E22CE]' : 'text-gray-700'} hover:underline`}
                  >
                    Add related skill pictures
                  </button>
                </li>
                <li className="flex items-center gap-1.5 rounded-md py-1.5 text-xs">
                  <button
                    type="button"
                    aria-pressed={suggestionChecks.elite}
                    onClick={() => setSuggestionChecks((p) => ({ ...p, elite: !p.elite }))}
                    className={`inline-flex items-center justify-center w-4 h-4 rounded-full border-2 shrink-0 leading-none ${suggestionChecks.elite ? 'bg-[#7E22CE] border-[#7E22CE] text-white hover:!bg-[#7E22CE] hover:!border-[#7E22CE]' : 'border-gray-300 bg-white hover:border-gray-400'} focus:outline-none`}
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
                    className={`${suggestionChecks.elite ? 'text-[#7E22CE]' : 'text-gray-700'} hover:underline`}
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
                        <Camera className="w-6 h-6 text-[#7E22CE]" />
                      </div>
                    }
                  />
                  <h3 className="text-base font-semibold text-gray-800">About You</h3>
                </div>
                <button onClick={() => { setEditVariant('about'); setShowEditModal(true); }} className="text-[#7E22CE] hover:underline text-sm">Edit</button>
              </div>
              <p className="text-gray-600 text-xs">Experience: {profile.years_experience} years</p>
              <p className="text-gray-700 text-sm mt-2">{profile.bio}</p>
            </div>

            <div className="rounded-lg border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-800">Skills & Pricing</h3>
                <button onClick={() => { setEditVariant('services'); setShowEditModal(true); }} className="text-[#7E22CE] hover:underline text-sm">Edit</button>
              </div>
              <div className="space-y-2">
                {profile.services.map((service) => {
                  const displayName = displayServiceName(service, hydrateCatalogNameById);

                  if (
                    process.env.NODE_ENV !== 'production' &&
                    !service.service_catalog_name &&
                    !hydrateCatalogNameById(service.service_catalog_id || '')
                  ) {
                    logger.warn('[service-name] missing catalog name (dashboard)', {
                      serviceCatalogId: service.service_catalog_id,
                    });
                  }

                  return (
                  <div key={service.id} className="flex justify-between items-center p-3 bg-white rounded-lg border border-gray-100">
                    <div>
                      <span className="font-medium text-gray-700">{displayName}</span>
                      {service.description && <p className="text-sm text-gray-600 mt-1">{service.description}</p>}
                    </div>
                    <span className="font-bold text-[#7E22CE] text-lg">${service.hourly_rate}/hr</span>
                  </div>
                );
                })}
              </div>
            </div>

            <div className="rounded-lg border border-gray-200 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-800">Service Areas</h3>
                <button onClick={() => { setEditVariant('areas'); setShowEditModal(true); }} className="text-[#7E22CE] hover:underline text-sm">Edit</button>
              </div>
              {(() => {
                const derivedBoroughs = profile ? getServiceAreaBoroughs(profile) : [];
                const areaSource = serviceAreaSelections.length > 0
                  ? serviceAreaSelections.map((item) => item.name)
                  : (serviceAreaNames && serviceAreaNames.length > 0
                    ? serviceAreaNames
                    : derivedBoroughs);
                const hasAreas = areaSource && areaSource.length > 0;
                return (
                  <div className="space-y-4">
                    {hasAreas ? (
                      <div className="flex flex-wrap gap-2">
                        {areaSource.map((area) => (
                          <span key={area} className="px-2 py-1 text-xs rounded-full bg-purple-50 text-[#7E22CE] border border-purple-200">{area}</span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-gray-500 text-sm">No service areas selected.</p>
                    )}
                    {preferredTeachingLocations.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Preferred Teaching Locations</p>
                        <div className="flex flex-wrap gap-2">
                          {preferredTeachingLocations.map((location) => {
                            const label = location.label?.trim() || location.address;
                            return (
                              <span
                                key={`teaching-${location.address}`}
                                className="px-2 py-1 text-xs rounded-full bg-blue-50 text-blue-700 border border-blue-200"
                                data-testid="preferred-teaching-chip"
                              >
                                {label}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    )}
                    {preferredPublicSpaces.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Preferred Public Spaces</p>
                        <div className="flex flex-wrap gap-2">
                          {preferredPublicSpaces.map((location) => (
                            <span
                              key={`public-${location.address}`}
                              className="px-2 py-1 text-xs rounded-full bg-green-50 text-green-700 border border-green-200"
                              data-testid="preferred-public-chip"
                            >
                              {location.address}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
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
          selectedServiceAreas={serviceAreaSelections}
          preferredTeaching={preferredTeachingLocations}
          preferredPublic={preferredPublicSpaces}
          onSave={handleAreasModalSave}
        />
      )}
      <Modal isOpen={showVerifyModal} onClose={() => setShowVerifyModal(false)} title="" size="xl">
        {/* Identity Verification section (matches onboarding step) */}
        <div className="space-y-4">
          <div className="grid grid-cols-[3rem_1fr] gap-4">
            <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
              <svg className="w-6 h-6 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-900 self-center">Identity Verification</h2>
            <p className="text-gray-600 mt-2 col-span-2">Verify your identity with a government-issued ID and a selfie</p>

            <div className="mt-2 col-span-2 grid grid-cols-[1fr_auto] gap-4 items-end">
              <div className="space-y-2 text-sm text-gray-500">
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
                <p className="text-xs text-gray-500 mt-2">Your information is safe and will only be used for verification purposes.</p>
              </div>

              <button
                onClick={async () => {
                try {
                  setShowVerifyModal(false);
                  const session = await createStripeIdentitySession();
                  try {
                    const pk = process.env['NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY'];
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
                className="inline-flex items-center justify-center w-56 whitespace-nowrap px-4 py-2 rounded-lg text-white bg-[#7E22CE] hover:bg-[#7E22CE] transition-colors font-medium"
              >
                Start Verification
              </button>
            </div>
          </div>

          {/* Divider removed to match onboarding look */}

          {/* Background Check (from verification page) - no border in modal */}
          <div className="p-0 mt-2">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                <svg className="w-5 h-5 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div className="flex-1">
                <h2 className="text-base font-semibold text-gray-900">Background Check</h2>
                <p className="text-gray-600 mt-1 text-sm">Upload your background check document</p>

                <div className="mt-2 grid grid-cols-[1fr_auto] items-end gap-4">
                  <div>
                    <p className="text-xs text-gray-500">We accept background checks from Checkr, Sterling, or NYC DOE.</p>
                    <p className="mt-2 text-xs text-gray-500">All uploaded files are securely encrypted and will remain confidential</p>
                    <div className="mt-4">
                      <p className="text-xs text-gray-500 whitespace-nowrap mb-1">File Requirements:</p>
                      <ul className="list-disc pl-5 text-xs text-gray-500 space-y-1">
                        <li className="whitespace-nowrap">Formats: PDF, JPG, PNG</li>
                        <li className="whitespace-nowrap">Maximum size: 10 MB</li>
                      </ul>
                    </div>
                  </div>
                  <div className="flex justify-end">
                    <label className="inline-flex items-center justify-center w-40 px-4 py-2.5 rounded-lg bg-purple-50 border border-purple-200 text-[#7E22CE] font-medium hover:bg-purple-100 transition-colors cursor-pointer">
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
                  </div>
                  {bgFileInfo && (
                    <div className="col-start-2 mt-3 flex items-center gap-2 text-sm text-green-700">
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
