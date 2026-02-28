// frontend/app/(auth)/instructor/dashboard/page.tsx
'use client';

import {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
  type ReactNode,
  type ComponentType,
  type SVGProps,
  type RefObject,
  type MutableRefObject,
} from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import Modal from '@/components/Modal';
import { Calendar, SquareArrowDownLeft, DollarSign, Eye, MessageSquare, Menu, X, ChevronDown, User } from 'lucide-react';
import { useInstructorAvailability } from '@/hooks/queries/useInstructorAvailability';
import { getCurrentWeekRange } from '@/types/common';
import { useInstructorBookings } from '@/hooks/queries/useInstructorBookings';
import EditProfileModal from '@/components/modals/EditProfileModal';
import { createStripeIdentitySession, createSignedUpload, fetchWithAuth } from '@/lib/api';
import { paymentService } from '@/services/api/payments';
import { logger } from '@/lib/logger';
import { InstructorProfile } from '@/types/instructor';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import { normalizeInstructorServices } from '@/lib/instructorServices';
import { getServiceAreaBoroughs } from '@/lib/profileServiceAreas';
import { httpPut } from '@/features/shared/api/http';
import { useInstructorRatingsQuery } from '@/hooks/queries/useRatings';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';
import { useInstructorServiceAreas } from '@/hooks/queries/useInstructorServiceAreas';
import { useInstructorEarnings } from '@/hooks/queries/useInstructorEarnings';
import { useStripeConnectStatus } from '@/hooks/queries/useStripeConnectStatus';
import { useQuery } from '@tanstack/react-query';
import { withApiBase } from '@/lib/apiBase';
import { fetchWithSessionRefresh } from '@/lib/auth/sessionRefresh';
import type { ConversationListResponse } from '@/types/conversation';
import { FoundingBadge } from '@/components/ui/FoundingBadge';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import type { ApiErrorResponse, components } from '@/features/shared/api/types';
import { extractApiErrorMessage } from '@/lib/apiErrors';

type DashboardLinkResponse = components['schemas']['DashboardLinkResponse'];
type InstantPayoutResponse = components['schemas']['InstantPayoutResponse'];

type NeighborhoodSelection = { neighborhood_id: string; name: string };
type PreferredTeachingLocation = { address: string; label?: string };
type PreferredPublicSpace = { address: string; label?: string };
type DashboardPanel = 'dashboard' | 'profile' | 'bookings' | 'earnings' | 'referrals' | 'reviews' | 'availability' | 'account';

const DASHBOARD_PANEL_KEYS = new Set<DashboardPanel>([
  'dashboard',
  'profile',
  'bookings',
  'earnings',
  'referrals',
  'reviews',
  'availability',
  'account',
]);

const isDashboardPanel = (value: string | null): value is DashboardPanel => {
  return value !== null && DASHBOARD_PANEL_KEYS.has(value as DashboardPanel);
};

const MOBILE_NAV_PRIMARY: Array<{ key: DashboardPanel; label: string }> = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'bookings', label: 'Bookings' },
  { key: 'availability', label: 'Availability' },
];

const MOBILE_NAV_SECONDARY: Array<{ key: DashboardPanel; label: string }> = [
  { key: 'profile', label: 'Profile' },
  { key: 'earnings', label: 'Earnings' },
  { key: 'referrals', label: 'Referrals' },
  { key: 'reviews', label: 'Reviews' },
  { key: 'account', label: 'Account' },
];

type IconComponent = ComponentType<SVGProps<SVGSVGElement>>;

function DashboardPopover({
  icon: Icon,
  label,
  isOpen,
  onToggle,
  children,
  containerRef,
  badgeCount,
}: {
  icon: IconComponent;
  label: string;
  isOpen: boolean;
  onToggle: () => void;
  children: ReactNode;
  /**
   * DOM ref used for positioning/portals. Nullable by design because refs are null until after mount.
   * Accepts both object and mutable refs.
   */
  containerRef?: RefObject<HTMLDivElement> | MutableRefObject<HTMLDivElement | null>;
  badgeCount?: number;
}) {
  const refProp = containerRef ?? undefined;
  const containerReady = Boolean(containerRef);

  const hasBadge = typeof badgeCount === 'number' && badgeCount > 0;
  const badgeLabel = hasBadge ? (badgeCount > 9 ? '9+' : String(badgeCount)) : '';
  const computedLabel = hasBadge ? `${label} (${badgeLabel} unread)` : label;
  return (
    <div className="relative" ref={refProp} data-container-ready={containerReady ? 'true' : 'false'}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={computedLabel}
        className="group relative inline-flex items-center justify-center w-10 h-10 rounded-full text-[#7E22CE] transition-colors duration-150 focus:outline-none select-none"
        title={label}
      >
        <Icon
          className="w-6 h-6 transition-colors group-hover:fill-current"
          style={{ fill: isOpen ? 'currentColor' : undefined }}
        />
        {hasBadge && (
          <span className="absolute -top-0.5 -right-0.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#7E22CE] px-1 text-[10px] font-semibold leading-none text-white">
            {badgeLabel}
          </span>
        )}
      </button>
      {isOpen && (
        <div role="menu" className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
          {children}
        </div>
      )}
    </div>
  );
}

export default function InstructorDashboardNew() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [profile, setProfile] = useState<InstructorProfile | null>(null);
  const [isHydratingProfile, setIsHydratingProfile] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editVariant] = useState<'about' | 'areas' | 'services' | 'full'>('full');
  // Delete profile modal removed
  const titleCardRef = useRef<HTMLDivElement | null>(null);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [sidebarOffset, setSidebarOffset] = useState<number>(0);
  const lastStableOffsetRef = useRef<number>(0);
  const [isOffsetFrozen, setIsOffsetFrozen] = useState(false);
  const [activePanel, setActivePanelState] = useState<DashboardPanel>(() => {
    const initialPanel = searchParams.get('panel');
    return isDashboardPanel(initialPanel) ? initialPanel : 'dashboard';
  });
  useEffect(() => {
    const paramPanel = searchParams.get('panel');
    if (isDashboardPanel(paramPanel)) {
      setActivePanelState((prev) => (prev === paramPanel ? prev : paramPanel));
    } else {
      setActivePanelState((prev) => (prev === 'dashboard' ? prev : 'dashboard'));
    }
  }, [searchParams]);

  const handlePanelChange = useCallback(
    (panel: DashboardPanel, options?: { replace?: boolean }) => {
      setActivePanelState(panel);
      const currentSearch = searchParams.toString();
      const currentHref = currentSearch ? `${pathname}?${currentSearch}` : pathname;

      const nextParams = new URLSearchParams(searchParams.toString());
      if (panel === 'dashboard') {
        nextParams.delete('panel');
      } else {
        nextParams.set('panel', panel);
      }
      const nextSearch = nextParams.toString();
      const nextHref = nextSearch ? `${pathname}?${nextSearch}` : pathname;

      if (nextHref === currentHref) {
        return;
      }

      const navOptions = { scroll: false };
      const useReplace = options?.replace ?? false;
      if (useReplace) {
        router.replace(nextHref, navOptions);
      } else {
        router.push(nextHref, navOptions);
      }
    },
    [pathname, router, searchParams]
  );

  // Notifications dropdown state (declare before any conditional returns)
  const notifRef = useRef<HTMLDivElement | null>(null);
  const [showNotifications, setShowNotifications] = useState(false);
  // Messages dropdown state
  const msgRef = useRef<HTMLDivElement | null>(null);
  const [showMessages, setShowMessages] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [showMoreMobile, setShowMoreMobile] = useState(false);
  // Conversations for badge/dropdown
  const { data: conversationList } = useQuery({
    queryKey: ['conversations', 'dashboard', 'active'],
    queryFn: async () => {
      const response = await fetchWithSessionRefresh(
        withApiBase('/api/v1/conversations?state=active&limit=50'),
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
        }
      );
      if (!response.ok) {
        throw new Error(`Failed to load conversations: ${response.status}`);
      }
      return response.json() as Promise<ConversationListResponse>;
    },
    // Poll so the badge updates when new messages arrive while the user sits on the dashboard
    refetchInterval: 10_000,
    refetchIntervalInBackground: true,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });
  const unreadConversations = (conversationList?.conversations ?? []).filter(
    (conv) => (conv.unread_count ?? 0) > 0
  );
  // Badge should reflect number of conversations with unread messages, not total unread messages
  const unreadConversationsCount = unreadConversations.length;
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      const outsideNotif = notifRef.current ? !notifRef.current.contains(target) : true;
      const outsideMsg = msgRef.current ? !msgRef.current.contains(target) : true;
      if (outsideNotif && outsideMsg) {
        setShowNotifications(false);
        setShowMessages(false);
      }
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, []);

  const ProfilePanel = useMemo(
    () => dynamic(() => import('../profile/embedded').then((m) => m.default), { ssr: false }),
    []
  );
  const BookingsPanel = useMemo(
    () => dynamic(() => import('../bookings/embedded').then((m) => m.default), { ssr: false }),
    []
  );
  const EarningsPanel = useMemo(
    () => dynamic(() => import('../earnings/embedded').then((m) => m.default), { ssr: false }),
    []
  );
  const ReferralsPanel = useMemo(
    () => dynamic(() => import('../referrals/embedded').then((m) => m.default), { ssr: false }),
    []
  );
  const ReviewsPanel = useMemo(
    () => dynamic(() => import('../reviews/embedded').then((m) => m.default), { ssr: false }),
    []
  );
  const AvailabilityPanel = useMemo(
    () => dynamic(() => import('../availability/embedded').then((m) => m.default), { ssr: false }),
    []
  );
  const AccountPanel = useMemo(
    () => dynamic(() => import('../settings/embedded').then((m) => m.default), { ssr: false }),
    []
  );

  const computeSidebarOffset = useCallback(() => {
    try {
      if (isOffsetFrozen) return;
      const grid = gridRef.current;
      // If profile/bookings is embedded, align to its first card element; otherwise align to dashboard title card
      const profileAnchor = typeof document !== 'undefined' ? document.getElementById('profile-first-card') : null;
      const bookingsAnchor = typeof document !== 'undefined' ? document.getElementById('bookings-first-card') : null;
      const earningsAnchor = typeof document !== 'undefined' ? document.getElementById('earnings-first-card') : null;
      const referralsAnchor = typeof document !== 'undefined' ? document.getElementById('referrals-first-card') : null;
      const reviewsAnchor = typeof document !== 'undefined' ? document.getElementById('reviews-first-card') : null;
      const availabilityAnchor = typeof document !== 'undefined' ? document.getElementById('availability-first-card') : null;
      const firstCard = activePanel === 'profile'
        ? (profileAnchor as HTMLElement | null)
        : activePanel === 'bookings'
          ? (bookingsAnchor as HTMLElement | null)
          : activePanel === 'earnings'
            ? (earningsAnchor as HTMLElement | null)
            : activePanel === 'referrals'
              ? (referralsAnchor as HTMLElement | null)
            : activePanel === 'reviews'
              ? (reviewsAnchor as HTMLElement | null)
              : activePanel === 'availability'
                ? (availabilityAnchor as HTMLElement | null)
          : titleCardRef.current;
      if (!grid || !firstCard) {
        // If profile is switching, use the last stable dashboard offset to avoid initial drop
        if (activePanel === 'profile' && lastStableOffsetRef.current > 0) {
          setSidebarOffset(lastStableOffsetRef.current);
        }
        return;
      }
      const gridTop = grid.getBoundingClientRect().top;
      const cardTop = firstCard.getBoundingClientRect().top;
      const delta = Math.max(0, Math.round(cardTop - gridTop));
      // Replicate Home behavior exactly: set absolute offset with minimal snapping (1px)
      const next = Math.abs(delta - lastStableOffsetRef.current) <= 1 ? lastStableOffsetRef.current : delta;
      lastStableOffsetRef.current = next;
      setSidebarOffset((prev) => (prev !== next ? next : prev));
    } catch {
      // Ignore measure errors; retain previous offset
    }
  }, [activePanel, isOffsetFrozen]);

  const computeSidebarOffsetRef = useRef(computeSidebarOffset);
  useEffect(() => {
    computeSidebarOffsetRef.current = computeSidebarOffset;
  }, [computeSidebarOffset]);

  useEffect(() => {
    computeSidebarOffset();
    const onResize = () => computeSidebarOffset();
    const onLoad = () => computeSidebarOffset();
    window.addEventListener('resize', onResize);
    window.addEventListener('load', onLoad);
    // Match home behavior: single early recompute
    const t1 = setTimeout(computeSidebarOffset, 0);
    let mo: MutationObserver | null = null;
    if (gridRef.current && typeof MutationObserver !== 'undefined') {
      mo = new MutationObserver(() => computeSidebarOffset());
      mo.observe(gridRef.current, { childList: true, subtree: true });
    }
    try {
      // Recompute after font loading as it can shift layout
      const fontsReady = document.fonts?.ready;
      if (fontsReady) {
        void fontsReady.then(() => computeSidebarOffset());
      }
    } catch {}
    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('load', onLoad);
      clearTimeout(t1);
      if (mo) mo.disconnect();
    };
  }, [computeSidebarOffset, activePanel]);

  // Freeze sidebar offset briefly when switching to embedded panels to avoid visible reflow
  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    const shouldFreeze =
      activePanel === 'profile' ||
      activePanel === 'bookings' ||
      activePanel === 'earnings' ||
      activePanel === 'referrals' ||
      activePanel === 'reviews' ||
      activePanel === 'availability';

    if (shouldFreeze) {
      setIsOffsetFrozen(true);
      timeoutId = setTimeout(() => {
        setIsOffsetFrozen(false);
        computeSidebarOffsetRef.current();
      }, 280);
    } else {
      setIsOffsetFrozen(false);
    }

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [activePanel]);

  // No overlay animations; keep load simple and stable
  // Use React Query for Stripe Connect status (deduplicates API calls)
  const {
    data: connectStatus,
    refetch: refetchConnectStatus,
    isRefetching: isRefreshingConnect,
  } = useStripeConnectStatus(true);

  const [isStartingStripeOnboarding, setIsStartingStripeOnboarding] = useState(false);
  const [serviceAreaSelections, setServiceAreaSelections] = useState<NeighborhoodSelection[]>([]);
  const [preferredTeachingLocations, setPreferredTeachingLocations] = useState<PreferredTeachingLocation[]>([]);
  const [preferredPublicSpaces, setPreferredPublicSpaces] = useState<PreferredPublicSpace[]>([]);
  const {
    data: instructorProfile,
    isLoading: isProfileLoading,
    error: profileQueryError,
    refetch: refetchInstructorProfile,
  } = useInstructorProfileMe(true);
  const { data: serviceAreaResponse } = useInstructorServiceAreas(Boolean(instructorProfile));
  const {
    data: earningsSummary,
    isLoading: isEarningsPending,
  } = useInstructorEarnings(Boolean(instructorProfile));
  const isLoading = isProfileLoading || isHydratingProfile;
  const isEarningsLoading = isEarningsPending && !earningsSummary;
  useEffect(() => {
    if (profileQueryError) {
      setError((profileQueryError as Error).message);
    }
  }, [profileQueryError]);

  useEffect(() => {
    // Type guard for error with status
    function getErrorStatus(error: unknown): number | undefined {
      if (error && typeof error === 'object' && 'status' in error) {
        const maybeStatus = (error as { status?: unknown }).status;
        return typeof maybeStatus === 'number' ? maybeStatus : undefined;
      }
      return undefined;
    }

    const status = getErrorStatus(profileQueryError);
    if (status === 401) {
      router.push('/login?redirect=/instructor/dashboard');
    }
  }, [profileQueryError, router]);
  const instructorUserId = instructorProfile?.user_id ?? profile?.user_id ?? '';
  const { data: ratingsData } = useInstructorRatingsQuery(instructorUserId);
  const reviewCount = ratingsData?.overall?.total_reviews ?? 0;
  const reviewAverageDisplay =
    ratingsData?.overall?.display_rating ??
    (typeof ratingsData?.overall?.rating === 'number'
      ? ratingsData.overall.rating.toFixed(1)
      : null);
  const reviewSubtitle =
    reviewCount > 0 ? `${reviewCount} review${reviewCount === 1 ? '' : 's'}` : 'Not yet available';
  const reviewAverageText =
    reviewCount > 0 && reviewAverageDisplay ? reviewAverageDisplay : '–';
  // Suggestions state removed; no longer used
  const [showVerifyModal, setShowVerifyModal] = useState(false);
  const [bgUploading, setBgUploading] = useState(false);
  const [bgFileInfo, setBgFileInfo] = useState<{ name: string; size: number } | null>(null);
  // Optional items removed; no longer used

  useEffect(() => {
    logger.info('Instructor dashboard (new) loaded');
  }, []);

  useEffect(() => {
    let ignore = false;
    if (!instructorProfile) {
      if (!isProfileLoading) {
        setProfile(null);
        setPreferredTeachingLocations([]);
        setPreferredPublicSpaces([]);
        setIsHydratingProfile(false);
      }
      return () => {
        ignore = true;
      };
    }
    setIsHydratingProfile(true);
    (async () => {
      try {
        if (!instructorProfile.user || !instructorProfile.services) {
          throw new Error('Invalid profile data received');
        }
        const profileRecord = instructorProfile as unknown as Record<string, unknown>;
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

        const serviceAreaBoroughs = getServiceAreaBoroughs(instructorProfile);

        logger.info('Instructor profile loaded successfully', {
          userId: instructorProfile.user_id,
          servicesCount: instructorProfile.services.length,
          boroughCount: serviceAreaBoroughs.length,
        });

        const normalizedServices = await normalizeInstructorServices(instructorProfile.services);
        if (ignore) return;
        setProfile({ ...instructorProfile, services: normalizedServices });
        setError(null);
      } catch (err) {
        if (!ignore) {
          logger.error('Error hydrating instructor profile', err);
          setPreferredTeachingLocations([]);
          setPreferredPublicSpaces([]);
          setProfile(null);
          setError(err instanceof Error ? err.message : 'An error occurred');
        }
      } finally {
        if (!ignore) {
          setIsHydratingProfile(false);
        }
      }
    })();
    return () => {
      ignore = true;
    };
  }, [instructorProfile, isProfileLoading]);

  useEffect(() => {
    if (!serviceAreaResponse?.items || serviceAreaResponse.items.length === 0) {
      setServiceAreaSelections([]);
      return;
    }
    const selectionMap = new Map<string, NeighborhoodSelection>();
    for (const item of serviceAreaResponse.items) {
      const id = item.neighborhood_id;
      const rawName = typeof item?.name === 'string' ? item.name.trim() : '';
      selectionMap.set(id, { neighborhood_id: id, name: rawName || id });
    }
    setServiceAreaSelections(Array.from(selectionMap.values()));
  }, [serviceAreaResponse]);

  // Left sidebar is inline with content; no fixed positioning logic

  // Weekly range for availability/bookings (Mon–Sun)
  const weekRange = getCurrentWeekRange(1);
  const { data: availability } = useInstructorAvailability(profile?.user_id || '', weekRange.start_date);
  const upcomingBookingsQuery = useInstructorBookings({
    status: 'CONFIRMED',
    upcoming: true,
    page: 1,
    enabled: Boolean(profile?.user_id),
  });
  const completedBookingsQuery = useInstructorBookings({
    status: 'COMPLETED',
    upcoming: false,
    page: 1,
    enabled: Boolean(profile?.user_id),
  });

  // Helpers to calculate minutes from HH:MM or HH:MM:SS
  const parseTimeToMinutes = useCallback((time: string): number => {
    const parts = (time || '').split(':');
    const h = parseInt(parts[0] || '0', 10);
    const m = parseInt(parts[1] || '0', 10);
    return (Number.isFinite(h) ? h : 0) * 60 + (Number.isFinite(m) ? m : 0);
  }, []);

  // useUnreadCount hook handles fetching (above) - React Query deduplicates calls

  const diffMinutes = useCallback((start: string, end: string): number => {
    const s = parseTimeToMinutes(start);
    const e = parseTimeToMinutes(end);
    return Math.max(0, e - s);
  }, [parseTimeToMinutes]);

  const completedBookingsCount = useMemo(
    () => Math.max(0, completedBookingsQuery.data?.total ?? 0),
    [completedBookingsQuery.data]
  );

  const upcomingWeekBookings = useMemo(() => {
    if (!Array.isArray(upcomingBookingsQuery.data?.items)) return [];
    return (upcomingBookingsQuery.data!.items as Array<{
      booking_date?: string;
      start_time?: string;
      end_time?: string;
    }>).filter(
      (booking) =>
        typeof booking.booking_date === 'string' &&
        booking.booking_date >= weekRange.start_date &&
        booking.booking_date <= weekRange.end_date
    );
  }, [upcomingBookingsQuery.data, weekRange.start_date, weekRange.end_date]);

  const bookedMinutes = useMemo(
    () =>
      upcomingWeekBookings.reduce((total, booking) => {
        const start = booking.start_time ?? '00:00';
        const end = booking.end_time ?? start;
        return total + diffMinutes(start, end);
      }, 0),
    [upcomingWeekBookings, diffMinutes]
  );

  const upcomingBookingsCount = upcomingWeekBookings.length;
  const hasUpcomingBookings = upcomingBookingsQuery.isLoading ? null : upcomingBookingsCount > 0;

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

  const availableHours = Math.round(availableMinutes / 60);
  const bookedHours = Math.round(bookedMinutes / 60);
  const formatCurrencyFromCents = (value?: number | null) => {
    if (typeof value !== 'number') return '$0.00';
    return `$${(value / 100).toFixed(2)}`;
  };
  const earningsCardValue = earningsSummary && typeof earningsSummary.total_earned === 'number'
    ? formatCurrencyFromCents(earningsSummary.total_earned)
    : (isEarningsLoading ? '—' : '$0.00');

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
    void refetchInstructorProfile();
    setShowEditModal(false);
  };

  const handleAreasModalSave = useCallback(async (payload: {
    neighborhoods: NeighborhoodSelection[];
    preferredTeaching: PreferredTeachingLocation[];
    preferredPublic: PreferredPublicSpace[];
  }) => {
    try {
      const neighborhoodIds = payload.neighborhoods.map((item) => item.neighborhood_id);
      await httpPut('/api/v1/addresses/service-areas/me', { neighborhood_ids: neighborhoodIds });
      await httpPut('/instructors/me', {
        preferred_teaching_locations: payload.preferredTeaching,
        preferred_public_spaces: payload.preferredPublic,
      });
      setServiceAreaSelections(payload.neighborhoods);
      setPreferredTeachingLocations(payload.preferredTeaching);
      setPreferredPublicSpaces(payload.preferredPublic);
      // no-op
    } catch (err) {
      logger.error('Failed to save service areas from dashboard', err);
      throw err;
    }
  }, []);

  // Public profile view button removed with title bar

  // After mount, show a client-rendered spinner while loading
  if (isLoading) {
    return (
      <div className="min-h-screen insta-dashboard-page flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#7E22CE]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen insta-dashboard-page">
        <header className="insta-dashboard-header px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link
              href="/instructor/dashboard"
              className="inline-block"
              onClick={() => {
                handlePanelChange('dashboard', { replace: true });
                setShowMessages(false);
                setShowNotifications(false);
                setIsMobileMenuOpen(false);
              }}
            >
              <span className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</span>
            </Link>
            <div className="pr-4">
              <UserProfileDropdown hideDashboardItem />
            </div>
          </div>
        </header>
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
          <div className="insta-surface-card p-6 text-center">
            <h1 className="text-2xl font-bold text-red-600 mb-4">Error</h1>
            <p className="text-gray-600 dark:text-gray-400 mb-6">{error}</p>
            <Link
              href="/signup?redirect=%2Finstructor%2Fonboarding%2Fstep-2"
              className="insta-primary-btn inline-block px-6 py-2.5 text-white rounded-lg"
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
    <div className="min-h-screen insta-dashboard-page">
      {/* Header - matching other pages */}
      <header className="insta-dashboard-header px-4 sm:px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link
            href="/instructor/dashboard"
            className="inline-block"
            onClick={() => {
              handlePanelChange('dashboard', { replace: true });
              setShowMessages(false);
              setShowNotifications(false);
              setIsMobileMenuOpen(false);
            }}
          >
            <span className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</span>
          </Link>
          <div className="flex items-center gap-2 pr-0 sm:pr-4">
            <DashboardPopover
              icon={MessageSquare}
              label="Messages"
              isOpen={showMessages}
              onToggle={() => {
                setShowMessages((prev) => !prev);
                setShowNotifications(false);
                setIsMobileMenuOpen(false);
              }}
              containerRef={msgRef}
              badgeCount={unreadConversationsCount}
            >
              <ul className="max-h-80 overflow-auto p-2 space-y-2">
                {unreadConversations.length === 0 ? (
                  <>
                    <li className="px-2 py-2 text-sm text-gray-600 dark:text-gray-400">
                      No unread messages.
                    </li>
                    <li>
                      <button
                        className="w-full text-left text-sm text-gray-700 dark:text-gray-300 px-2 py-2 hover:bg-gray-50 rounded"
                        onClick={() => {
                          setShowMessages(false);
                          router.push('/instructor/messages');
                        }}
                      >
                        Open inbox
                      </button>
                    </li>
                  </>
                ) : (
                  unreadConversations.map((conv) => {
                    const otherName = `${conv.other_user.first_name} ${conv.other_user.last_initial}.`;
                    const preview = conv.last_message?.content || 'New message';
                    return (
                      <li key={conv.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setShowMessages(false);
                            router.push(`/instructor/messages?conversation=${conv.id}`);
                          }}
                          className="w-full rounded-lg px-3 py-2 text-left hover:bg-gray-50"
                        >
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{otherName}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{preview}</p>
                        </button>
                      </li>
                    );
                  })
                )}
              </ul>
            </DashboardPopover>
            <NotificationBell
              isOpen={showNotifications}
              onOpenChange={(open) => {
                setShowNotifications(open);
                if (open) {
                  setShowMessages(false);
                }
                setIsMobileMenuOpen(false);
              }}
              containerRef={notifRef}
            />
            <UserProfileDropdown hideDashboardItem />
            <button
              type="button"
              className="md:hidden p-2 rounded-lg text-[#7E22CE] border border-transparent focus:outline-none focus:ring-0 focus-visible:ring-0 hover:bg-transparent active:bg-transparent"
              aria-label={isMobileMenuOpen ? 'Close dashboard navigation menu' : 'Open dashboard navigation menu'}
              aria-expanded={isMobileMenuOpen}
              onClick={() => {
                setIsMobileMenuOpen((prev) => {
                  const next = !prev;
                  if (!next) setShowMoreMobile(false);
                  return next;
                });
              }}
              style={{ WebkitTapHighlightColor: 'transparent' }}
            >
              {isMobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
            </button>
          </div>
        </div>
        {isMobileMenuOpen && (
          <nav className="mt-4 border-t border-gray-200 dark:border-gray-700 pt-4 md:hidden" aria-label="Instructor navigation">
            <div className="space-y-4">
              <div>
                <div className="px-4 pb-2 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Quick access</div>
                <ul className="space-y-2">
                  {MOBILE_NAV_PRIMARY.map((item) => (
                    <li key={item.key}>
                      <button
                        type="button"
                        onClick={() => {
                          handlePanelChange(item.key);
                          setIsMobileMenuOpen(false);
                          setShowMoreMobile(false);
                        }}
                        className={`w-full text-left px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                          activePanel === item.key
                            ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 border border-purple-200 dark:border-purple-700'
                            : 'text-gray-700 dark:text-gray-300 dark:text-gray-200 hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                        }`}
                        aria-current={activePanel === item.key ? 'page' : undefined}
                      >
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="border-t border-gray-200 dark:border-gray-700 pt-3">
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-400 dark:text-gray-300 hover:text-[#7E22CE] dark:hover:text-purple-300"
                  onClick={() => setShowMoreMobile((prev) => !prev)}
                  aria-expanded={showMoreMobile}
                  aria-controls="mobile-nav-more"
                >
                  More tools
                  <ChevronDown className={`h-4 w-4 transition-transform ${showMoreMobile ? 'rotate-180' : ''}`} aria-hidden="true" />
                </button>
                {showMoreMobile && (
                  <ul id="mobile-nav-more" className="mt-2 space-y-2 px-1">
                    {MOBILE_NAV_SECONDARY.map((item) => (
                      <li key={item.key}>
                        <button
                          type="button"
                          onClick={() => {
                            handlePanelChange(item.key);
                            setIsMobileMenuOpen(false);
                            setShowMoreMobile(false);
                          }}
                          className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                            activePanel === item.key
                              ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 border border-purple-200 dark:border-purple-700'
                              : 'text-gray-700 dark:text-gray-300 dark:text-gray-200 hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                          }`}
                          aria-current={activePanel === item.key ? 'page' : undefined}
                        >
                          {item.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </nav>
        )}
      </header>

      {/* Sidebar placed inline next to title card, matching student layout */}
      {/* Removed duplicate standalone sidebar to avoid layout duplication */}

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Removed extra top header and snapshot cards to avoid duplicates */}

        {/* Main content as 2-column grid: sidebar + content (match student dashboard) */}
        <div ref={gridRef} className="grid grid-cols-12 gap-6">
          {/* Sidebar (duplicate for small screens hidden above) */}
          <aside className="hidden md:block col-span-12 md:col-span-3" style={{ marginTop: sidebarOffset }}>
            <div className="insta-surface-card p-4">
              <nav>
                <ul className="space-y-1">
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('dashboard')}
                      aria-current={activePanel === 'dashboard' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'dashboard'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Dashboard
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('account')}
                      aria-current={activePanel === 'account' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'account'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Account
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('profile')}
                      aria-current={activePanel === 'profile' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'profile'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Instructor Profile
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('bookings')}
                      aria-current={activePanel === 'bookings' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'bookings'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Bookings
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('earnings')}
                      aria-current={activePanel === 'earnings' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'earnings'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Earnings
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('referrals')}
                      aria-current={activePanel === 'referrals' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'referrals'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Referrals
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('availability')}
                      aria-current={activePanel === 'availability' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'availability'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Availability
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => handlePanelChange('reviews')}
                      aria-current={activePanel === 'reviews' ? 'page' : undefined}
                      className={`w-full text-left block px-3 py-2 rounded-md transition-transform transition-colors duration-150 transform ${
                        activePanel === 'reviews'
                          ? 'bg-purple-50 dark:bg-purple-900/30 text-[#7E22CE] dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-700'
                          : 'text-gray-800 dark:text-gray-200 hover:scale-[1.02] hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-[#7E22CE] dark:hover:text-purple-300'
                      }`}
                    >
                      Reviews
                    </button>
                  </li>
                </ul>
              </nav>
            </div>
          </aside>
          <section className="col-span-12 md:col-span-9">
            {activePanel === 'dashboard' && (
              <>

        {/* Welcome bar */}
        <SectionHeroCard
          ref={titleCardRef}
          icon={User}
          headingAs="h1"
          title={`Welcome back, ${profile.user?.first_name || 'Instructor'}!`}
          titleNode={
            <span className="flex flex-wrap items-center gap-3">
              <span>Welcome back, {profile.user?.first_name || 'Instructor'}!</span>
              {profile?.is_founding_instructor ? <FoundingBadge size="md" /> : null}
            </span>
          }
          titleClassName="text-3xl font-bold text-gray-800 dark:text-gray-100"
          subtitle="Your profile, schedule, and earnings at a glance"
          subtitleClassName="text-gray-600 dark:text-gray-400 text-sm"
          actions={(() => {
            const releaseTs = Date.UTC(2025, 11, 1, 0, 0, 0);
            const isEnabled = Date.now() >= releaseTs;
            return (
              <button
                onClick={() => { if (profile) router.push(`/instructors/${profile.user_id}`); }}
                disabled={!isEnabled}
                aria-disabled={!isEnabled}
                title={isEnabled ? 'View your public instructor page' : 'Public profile available Dec 1, 2025'}
                className={`w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isEnabled
                    ? 'insta-secondary-btn'
                    : 'bg-gray-100 border border-gray-300 text-gray-400 dark:text-gray-400 cursor-not-allowed dark:bg-gray-800/70 dark:border-gray-700 dark:text-gray-500 dark:text-gray-400'
                }`}
              >
                <Eye className="h-4 w-4" />
                <span>Public profile</span>
              </button>
            );
          })()}
        />

        {/* Snapshot Cards directly under header */}
        <h2 className="sr-only">Overview</h2>
        <div className="grid grid-cols-3 gap-3 sm:gap-6 mb-8">
          {/* Bookings card - clickable button, navigates to past tab since it shows completed count */}
          <button
            onClick={() => router.push('/instructor/dashboard?panel=bookings&tab=past', { scroll: false })}
            className="stat-card insta-dashboard-stat-card group block h-32 w-full rounded-md p-3 text-left transition-all hover:border-purple-300 dark:hover:border-purple-600 focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] sm:h-40 sm:rounded-lg sm:p-6"
            aria-label="Open bookings"
          >
            <div className="flex items-start justify-between h-full">
              <div>
                <h3 className="text-sm sm:text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1 sm:mb-2 group-hover:text-[#7E22CE] dark:group-hover:text-purple-300">Bookings</h3>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-gray-100 dark:text-white group-hover:text-gray-900 dark:text-gray-100 dark:group-hover:text-white">{completedBookingsCount}</p>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 group-hover:text-gray-600 dark:text-gray-400 dark:group-hover:text-gray-300 mt-1">
                  {(hasUpcomingBookings === false || completedBookingsCount === 0) ? 'No lessons scheduled today' : '\u00A0'}
                </p>
              </div>
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Calendar className="w-5 h-5 sm:w-6 sm:h-6 text-[#7E22CE]" />
              </div>
            </div>
          </button>

          {/* Earnings card - clickable with outline icon */}
          <button
            onClick={() => handlePanelChange('earnings')}
            className="stat-card insta-dashboard-stat-card group block w-full text-left rounded-md sm:rounded-lg p-3 sm:p-6 hover:border-purple-300 dark:hover:border-purple-600 h-32 sm:h-40 transition-all focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
            aria-label="Open earnings"
          >
            <div className="flex items-start justify-between h-full">
              <div>
                <h3 className="text-sm sm:text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1 sm:mb-2 group-hover:text-[#7E22CE] dark:group-hover:text-purple-300">Earnings</h3>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-gray-100 dark:text-white group-hover:text-gray-900 dark:text-gray-100 dark:group-hover:text-white">{earningsCardValue}</p>
              </div>
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <DollarSign className="w-5 h-5 sm:w-6 sm:h-6 text-[#7E22CE]" />
              </div>
            </div>
          </button>
          {/* Reviews card - clickable with outline icon */}
          <button
            onClick={() => handlePanelChange('reviews')}
            className="stat-card insta-dashboard-stat-card group block w-full text-left rounded-md sm:rounded-lg p-3 sm:p-6 hover:border-purple-300 dark:hover:border-purple-600 h-32 sm:h-40 transition-all focus:outline-none focus:ring-2 focus:ring-[#D4B5F0]"
            aria-label="Open reviews"
          >
            <div className="flex items-start justify-between h-full">
              <div>
                <h3 className="text-sm sm:text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1 sm:mb-2 group-hover:text-[#7E22CE] dark:group-hover:text-purple-300">Reviews</h3>
                <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-gray-100 dark:text-white group-hover:text-gray-900 dark:text-gray-100 dark:group-hover:text-white" data-testid="reviews-avg">
                  {reviewAverageText}
                </p>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 group-hover:text-gray-600 dark:text-gray-400 dark:group-hover:text-gray-300 mt-1" data-testid="reviews-count">
                  {reviewSubtitle}
                </p>
              </div>
              <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <svg className="w-5 h-5 sm:w-6 sm:h-6 text-[#7E22CE]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                </svg>
              </div>
            </div>
          </button>
          {/* Messages and Notifications stat cards removed per request */}
        </div>

        {/* Quick Actions (removed; Delete Profile moved into Profile card) */}

        <div className="mb-8 grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
          {/* Stripe Status Card */}
          <div id="payments-setup" className="insta-surface-card p-5 sm:p-6 h-full flex flex-col relative">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-start gap-3">
                <div className="relative group">
                  <button
                    type="button"
                    onClick={async () => {
                      if (isRefreshingConnect) return;
                      try {
                        await refetchConnectStatus();
                        try { (await import('sonner')).toast?.info?.('Status refreshed'); } catch {}
                      } catch {
                        try { (await import('sonner')).toast?.error?.('Failed to refresh status'); } catch {}
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
                    className="pointer-events-none absolute z-50 left-1/2 -translate-x-1/2 top-full mt-2 whitespace-nowrap rounded-md bg-white text-gray-800 dark:text-gray-200 text-xs shadow-lg border border-gray-200 px-2 py-1 opacity-0 translate-y-1 group-hover:opacity-100 group-focus-within:opacity-100 group-hover:translate-y-0 group-focus-within:translate-y-0 transition-all duration-150"
                  >
                    Refresh status
                  </div>
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Payments Setup</h2>
                  <p className="text-gray-600 dark:text-gray-400 text-xs mt-0.5">Manage your payouts securely</p>
                  <p className="text-gray-500 dark:text-gray-400 text-[11px]">Powered by Stripe</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2.5 py-1 rounded-md border ${connectStatus && connectStatus.charges_enabled && connectStatus.details_submitted ? 'bg-green-50 text-green-700 border-green-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                  {connectStatus && connectStatus.charges_enabled && connectStatus.details_submitted ? 'Connected' : 'Action required'}
                </span>
              </div>
            </div>
              <p className="text-gray-600 dark:text-gray-400 text-sm mb-4">Your Stripe account setup status.</p>
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
                    <li className={`flex items-center gap-2 text-sm ${chargesEnabled ? 'text-gray-700 dark:text-gray-300' : 'text-gray-500 dark:text-gray-400'}`}>
                      {chargesEnabled ? (
                        <svg className="w-4 h-4 text-[#7E22CE]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Payments enabled</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${detailsSubmitted ? 'text-gray-700 dark:text-gray-300' : 'text-gray-500 dark:text-gray-400'}`}>
                      {detailsSubmitted ? (
                        <svg className="w-4 h-4 text-[#7E22CE]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Bank details verified</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${payoutsEnabled ? 'text-gray-700 dark:text-gray-300' : 'text-gray-500 dark:text-gray-400'}`}>
                      {payoutsEnabled ? (
                        <svg className="w-4 h-4 text-[#7E22CE]" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                      )}
                      <span>Payouts active</span>
                    </li>
                    <li className={`flex items-center gap-2 text-sm ${onboardingCompleted ? 'text-gray-700 dark:text-gray-300' : 'text-gray-500 dark:text-gray-400'}`}>
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
                    <div className="mt-3 text-xs text-gray-600 dark:text-gray-400">Finish Stripe setup to start receiving payouts.</div>
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
            <div className="mt-5 flex flex-col sm:flex-row gap-3">
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
                  className="insta-secondary-btn inline-flex items-center px-3 py-2 text-sm rounded-lg disabled:opacity-60"
                >
                  {isStartingStripeOnboarding ? 'Opening…' : 'Complete Stripe onboarding'}
                </button>
              )}
              {/* Payouts and Instant Payout */}
              <div className="mt-auto border-t border-gray-200 pt-4">
                <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-1">Stripe Payouts</h3>
                <p className="text-gray-600 dark:text-gray-400 text-xs mb-2">Access your Stripe Express dashboard to view payouts and account settings.</p>
                <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-3 sm:justify-end">
                  <button
                    onClick={async () => {
                      try {
                        // Refresh status and get latest data
                        const { data: resp } = await refetchConnectStatus();
                        if (!resp || !(resp.charges_enabled && resp.details_submitted)) {
                          alert('Your Stripe onboarding is not completed yet. Please finish onboarding first.');
                          return;
                        }
                        const dl = await fetchWithAuth('/api/v1/payments/connect/dashboard');
                        if (dl.ok) {
                          const data = (await dl.json()) as DashboardLinkResponse;
                          window.open(data.dashboard_url, '_blank');
                        } else {
                          const err = (await dl.json().catch(() => ({}))) as ApiErrorResponse;
                          alert(`Unable to open Stripe dashboard: ${extractApiErrorMessage(err, dl.statusText)}`);
                        }
                      } catch {
                        alert('Unable to open Stripe dashboard right now.');
                      }
                    }}
                    className="insta-secondary-btn inline-flex items-center justify-center h-10 px-4 text-base rounded-lg w-full sm:w-auto"
                  >
                    View Payouts
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        const res = await fetchWithAuth('/api/v1/payments/connect/instant-payout', { method: 'POST' });
                        if (!res.ok) {
                          const err = (await res.json().catch(() => ({}))) as ApiErrorResponse;
                          alert(`Instant payout failed: ${extractApiErrorMessage(err, res.statusText)}`);
                          return;
                        }
                        const data = (await res.json()) as InstantPayoutResponse;
                        alert(`Instant payout requested: ${data.payout_id || 'OK'}`);
                      } catch {
                        alert('Instant payout request error');
                      }
                    }}
                    className="insta-primary-btn inline-flex items-center justify-center h-10 px-4 text-base rounded-lg text-white whitespace-nowrap w-full sm:w-auto sm:min-w-[13rem]"
                  >
                    Request Instant Payout
                  </button>
                </div>
          </div>
        </div>
          </div>

        {/* Manage Availability card (only icon is clickable) */}
          <div className="insta-surface-card p-5 sm:p-6 hover:shadow-md transition-shadow h-full flex flex-col relative">
            <div className="flex items-start gap-4 w-full">
              <button
                onClick={() => handlePanelChange('availability')}
                aria-label="Manage Availability"
                className="group relative w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-[#D4B5F0] transition shrink-0 overflow-hidden"
              >
                <span className="absolute inset-0 rounded-full bg-gray-100 opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
                <Calendar className="relative w-6 h-6 text-[#7E22CE] transition-transform duration-150 ease-out group-hover:scale-110" />
              </button>
              <div>
                <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300">Manage Availability</h3>
                <p className="text-gray-600 dark:text-gray-400 text-sm">Set your weekly schedule and available hours</p>
              </div>
            </div>
            <div className="mt-8 sm:mt-10 flex items-center gap-8 sm:gap-12 justify-center">
              <div className="flex flex-col items-center">
                <div className="w-28 h-28 rounded-full bg-purple-50 border border-purple-200 text-[#7E22CE] flex items-center justify-center text-2xl font-bold" title="Available hours this week">
                  {availableHours}h
                </div>
                <span className="mt-2 text-sm text-gray-600 dark:text-gray-400">Available</span>
              </div>
              <div className="flex flex-col items-center">
                <div className="w-28 h-28 rounded-full bg-gray-50 border border-gray-200 text-gray-700 dark:text-gray-300 flex items-center justify-center text-2xl font-bold" title="Booked hours this week">
                  {bookedHours}h
                </div>
                <span className="mt-2 text-sm text-gray-600 dark:text-gray-400">Booked</span>
              </div>
          </div>
            <div className="mt-auto border-t border-gray-200 pt-4">
            <div className="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-3 sm:justify-end">
              <button
                type="button"
                className="insta-primary-btn inline-flex items-center justify-center h-10 px-4 text-base rounded-lg text-white whitespace-nowrap w-full sm:w-auto sm:min-w-[13rem]"
                onClick={() => handlePanelChange('availability')}
              >
                Open Calendar
              </button>
            </div>
          </div>
          </div>
        </div>



        {/* Action row removed per request */}

      </>
            )}
            {activePanel === 'account' && (
              <div className="min-h-[60vh] overflow-visible">
                <AccountPanel />
              </div>
            )}
            {activePanel === 'profile' && (
              <div className="min-h-[60vh] overflow-visible">
                <ProfilePanel />
              </div>
            )}
            {activePanel === 'bookings' && (
              <div className="min-h-[60vh] overflow-visible">
                <BookingsPanel />
              </div>
            )}
            {activePanel === 'earnings' && (
              <div className="min-h-[60vh] overflow-visible">
                <EarningsPanel />
              </div>
            )}
            {activePanel === 'referrals' && (
              <div className="min-h-[60vh] overflow-visible">
                <ReferralsPanel />
              </div>
            )}
            {activePanel === 'reviews' && (
              <div className="min-h-[60vh] overflow-visible">
                <ReviewsPanel />
              </div>
            )}
            {activePanel === 'availability' && (
              <div className="min-h-[60vh] overflow-visible">
                <AvailabilityPanel />
              </div>
            )}
      </section>
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
          instructorProfile={instructorProfile ?? null}
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
            <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300 self-center">Identity Verification</h2>
            <p className="text-gray-600 dark:text-gray-400 mt-2 col-span-2">Verify your identity with a government-issued ID and a selfie</p>

            <div className="mt-2 col-span-2 grid grid-cols-[1fr_auto] gap-4 items-end">
              <div className="space-y-2 text-sm text-gray-500 dark:text-gray-400">
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
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Your information is safe and will only be used for verification purposes.</p>
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
                className="insta-primary-btn inline-flex items-center justify-center w-56 whitespace-nowrap px-4 py-2 rounded-lg text-white transition-colors font-medium"
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
                <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-300">Background Check</h2>
                <p className="text-gray-600 dark:text-gray-400 mt-1 text-sm">Upload your background check document</p>

                <div className="mt-2 grid grid-cols-[1fr_auto] items-end gap-4">
                  <div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">We accept background checks from Checkr, Sterling, or NYC DOE.</p>
                    <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">All uploaded files are securely encrypted and will remain confidential</p>
                    <div className="mt-4">
                      <p className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap mb-1">File Requirements:</p>
                      <ul className="list-disc pl-5 text-xs text-gray-500 dark:text-gray-400 space-y-1">
                        <li className="whitespace-nowrap">Formats: PDF, JPG, PNG</li>
                        <li className="whitespace-nowrap">Maximum size: 10 MB</li>
                      </ul>
                    </div>
                  </div>
                  <div className="flex justify-end">
                    <label className="insta-secondary-btn inline-flex items-center justify-center w-40 px-4 py-2.5 rounded-lg font-medium transition-colors cursor-pointer">
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
                            const uploadHeaders = signed.headers ?? {};
                            const putRes = await fetch(signed.upload_url, {
                              method: 'PUT',
                              headers: uploadHeaders,
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
      {/* Delete profile modal removed per request */}
    </div>
  );
}
