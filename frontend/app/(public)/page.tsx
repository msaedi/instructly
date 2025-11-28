// frontend/app/(public)/page.tsx
'use client';

import { useState, useEffect, useLayoutEffect } from 'react';
// import removed; background handled globally
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import Image from 'next/image';
import { type TopServiceSummary } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import { BRAND_LEGAL_NAME } from '@/lib/branding';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { hasRole } from '@/features/shared/hooks/useAuth.helpers';
import { RoleName, SearchType } from '@/types/enums';
import { NotificationBar } from '@/components/NotificationBar';
import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { useFeaturedServices } from '@/hooks/queries/useHomepage';
import { useServiceCategories } from '@/hooks/queries/useServices';
import { publicApi } from '@/features/shared/api/client';
import { getActivityBackground } from '@/lib/services/assetService';
import {
  Search,
  Zap,
  TrendingUp,
  Star,
  MapPin,
  Clock,
  Shield,
  DollarSign,
  CheckCircle,
  Globe,
  Music,
  Dumbbell,
  Sparkles,
  BookOpen,
  Palette,
  Baby,

  X,
} from 'lucide-react';
import { recordSearch } from '@/lib/searchTracking';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { useBeta } from '@/contexts/BetaContext';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';

const LEGAL_FOOTER_LINK_CLASSES =
  'text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400 no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#7E22CE]';

const HERO_PANEL_SIZE = 400;

const ensureHeroPanelSize = (url: string | null): string | null => {
  if (!url) return null;
  const marker = '/cdn-cgi/image/';
  const markerIndex = url.indexOf(marker);
  if (markerIndex === -1) {
    return url;
  }

  const paramsStart = markerIndex + marker.length;
  const paramsEnd = url.indexOf('/', paramsStart);
  if (paramsEnd === -1) {
    return url;
  }

  const rawParams = url.slice(paramsStart, paramsEnd).split(',');
  const filteredParams = rawParams.filter(
    (param) => !param.startsWith('width=') && !param.startsWith('height=')
  );
  filteredParams.push(`width=${HERO_PANEL_SIZE}`, `height=${HERO_PANEL_SIZE}`);

  return `${url.slice(0, paramsStart)}${filteredParams.join(',')}${url.slice(paramsEnd)}`;
};

const UpcomingLessons = dynamic(
  () => import('@/components/UpcomingLessons').then((mod) => mod.UpcomingLessons),
  {
    ssr: false,
    loading: () => (
      <section className="py-12" aria-hidden="true">
        <div className="max-w-7xl mx-auto px-4">
          <div className="h-40 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
        </div>
      </section>
    ),
  }
);

const BookAgain = dynamic(
  () => import('@/components/BookAgain').then((mod) => mod.BookAgain),
  {
    ssr: false,
    loading: () => (
      <section className="py-16 bg-transparent dark:bg-transparent" aria-hidden="true">
        <div className="max-w-7xl mx-auto px-4">
          <div className="h-48 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
        </div>
      </section>
    ),
  }
);

const RecentSearches = dynamic(
  () => import('@/components/RecentSearches').then((mod) => mod.RecentSearches),
  {
    ssr: false,
    loading: () => <div className="min-h-[140px]" aria-hidden="true" />,
  }
);

const PrivacySettings = dynamic(
  () => import('@/components/PrivacySettings').then((mod) => mod.PrivacySettings),
  {
    ssr: false,
    loading: () => <div className="min-h-[120px]" aria-hidden="true" />,
  }
);

export default function HomePage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('arts');
  const [hoveredCategory, setHoveredCategory] = useState<string | null>(null);
  const [isTouchDevice, setIsTouchDevice] = useState(false);
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);
  const [userHasBookingHistory, setUserHasBookingHistory] = useState<boolean | null>(null);
  const [isClient, setIsClient] = useState(false);
  const [hasSessionCookie, setHasSessionCookie] = useState(false);
  const router = useRouter();
  const { user, isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const isInstructor = isAuthenticated && hasRole(user, RoleName.INSTRUCTOR);

  // Use React Query hook for instructor profile (deduplicates API calls)
  const { data: instructorProfile } = useInstructorProfileMe(isInstructor);
  const isInstructorLive = instructorProfile?.is_live ?? null;
  const { config } = useBeta();
  const hideStudentUi = config.site === 'beta' && config.phase === 'instructor_only';
  const shouldShowBookAgain =
    isAuthenticated && !isInstructor && (userHasBookingHistory === null || userHasBookingHistory);
  const shouldReserveNotificationBarSpace =
    (hasSessionCookie && isAuthLoading) || isAuthenticated;

  // React Query hooks for fetching data with caching
  // These prevent duplicate API calls and improve performance
  const { data: topServicesData } = useFeaturedServices();
  const { data: categoriesData } = useServiceCategories();

  // Kids services - inline query (no dedicated hook exists yet)
  const { data: kidsServicesData } = useQuery({
    queryKey: queryKeys.services.kidsAvailable,
    queryFn: async () => {
      const response = await publicApi.getKidsAvailableServices();
      if (response.error) {
        throw new Error(response.error);
      }
      return response.data;
    },
    staleTime: CACHE_TIMES.STATIC, // 1 hour cache
  });

  // Process the cached data into the format the component expects
  const categoryServices = topServicesData ? (() => {
    const servicesMap: Record<string, TopServiceSummary[]> = {};
    topServicesData.categories.forEach((category) => {
      servicesMap[category.slug] = category.services;
    });
    return servicesMap;
  })() : {};

  const kidsServices = kidsServicesData || [];
  const categoriesFromDb = categoriesData || [];
  const heroLeftImageSrc = ensureHeroPanelSize(getActivityBackground('home', 'desktop'));
  const heroRightImageSrc = ensureHeroPanelSize(getActivityBackground('music', 'desktop'));
  const sessionCookiePrefix = '__Host-sid';

  useLayoutEffect(() => {
    if (typeof document === 'undefined') return;
    try {
      const hasCookie = document.cookie.split('; ').some((cookie) => cookie.startsWith(sessionCookiePrefix));
      setHasSessionCookie(hasCookie);
    } catch {
      setHasSessionCookie(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthLoading && !isAuthenticated) {
      setHasSessionCookie(false);
    }
  }, [isAuthenticated, isAuthLoading]);

  // Set isClient to true after mount to avoid hydration issues
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Restore previously selected category when returning from search/services
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const saved = sessionStorage.getItem('homeSelectedCategory');
    if (saved) {
      // Validate against known categories
      const valid = ['arts', 'sports-fitness', 'tutoring', 'language', 'music', 'kids', 'hidden-gems'];
      if (valid.includes(saved)) {
        setSelectedCategory(saved);
        setHoveredCategory(null);
      }
    }
  }, [isClient]);

  // Fetch top services on mount (client-only) to avoid SSR/client hook order issues

  // Note: Do not early-return before all hooks have run; gate rendering in JSX instead

  // Map backend icon_name/slug to Lucide icon components
  const ICON_MAP: Record<string, React.ComponentType> = {
    'palette': Palette,
    'arts': Palette,
    'dumbbell': Dumbbell,
    'sports-fitness': Dumbbell,
    'book-open': BookOpen,
    'book': BookOpen,
    'tutoring': BookOpen,
    'globe': Globe,
    'language': Globe,
    'music': Music,
    'music-note': Music,
    'baby': Baby,
    'child': Baby,
    'kids': Baby,
    'sparkles': Sparkles,
    'hidden-gems': Sparkles,
  };

  const categories = (categoriesFromDb && categoriesFromDb.length > 0)
    ? [...categoriesFromDb]
        .sort((a, b) => (a.display_order ?? 999) - (b.display_order ?? 999))
        .map((c) => ({
          icon: ICON_MAP[c.icon_name || c.slug] || Sparkles,
          name: c.name,
          slug: c.slug,
          subtitle: c.slug === 'kids' ? '' : (c.subtitle || ''),
        }))
    : [
        { icon: Palette, name: 'Arts', slug: 'arts', subtitle: 'Performing Visual Applied' },
        { icon: Dumbbell, name: 'Sports & Fitness', slug: 'sports-fitness', subtitle: '' },
        { icon: BookOpen, name: 'Tutoring', slug: 'tutoring', subtitle: 'Academic STEM Tech' },
        { icon: Globe, name: 'Language', slug: 'language', subtitle: '' },
        { icon: Music, name: 'Music', slug: 'music', subtitle: 'Instrument Voice Theory' },
        { icon: Baby, name: 'Kids', slug: 'kids', subtitle: '' },
        { icon: Sparkles, name: 'Hidden Gems', slug: 'hidden-gems', subtitle: '' },
      ];

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      // Track navigation source
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('navigationFrom', '/');
        logger.debug('Set navigation source from homepage search', {
          navigationFrom: '/',
          query: searchQuery,
        });
      }

      // Don't track here - let the search page track with correct results count
      router.push(`/search?q=${encodeURIComponent(searchQuery)}&from=home`);
    }
  };

  // Instructor live status now loaded via useInstructorProfileMe hook above

  // Detect touch device
  useEffect(() => {
    setIsTouchDevice('ontouchstart' in window || navigator.maxTouchPoints > 0);
  }, []);

  // Background handled globally via GlobalBackground

  const availableNow = [
    {
      name: 'Sarah C.',
      subject: 'Piano',
      rate: 75,
      rating: 4.9,
      location: 'Midtown',
      nextAvailable: '2:00 PM',
    },
    {
      name: 'Marcus R.',
      subject: 'Spanish',
      rate: 65,
      rating: 4.8,
      location: 'Brooklyn',
      nextAvailable: '3:30 PM',
    },
  ];

  const trending = [
    { name: 'Spanish Lessons', change: 45 },
    { name: 'LSAT Prep', change: 38 },
    { name: 'Guitar Lessons', change: 31 },
    { name: 'Python Coding', change: 28 },
    { name: 'Yoga & Meditation', change: 24 },
  ];

  const testimonials = [
    {
      quote: 'Sarah helped me go from beginner to playing my favorite songs in 6 weeks!',
      author: 'Emma K.',
      rating: 5,
    },
    {
      quote: 'I went from struggling with Spanish to conversational in 3 months!',
      author: 'David L.',
      rating: 5,
    },
    {
      quote: 'Found the best yoga instructor in 5 minutes. Life changing!',
      author: 'Marcus W.',
      rating: 5,
    },
  ];

  return (
    <div className="min-h-screen relative" suppressHydrationWarning>
      {/* Navigation - matching search results page */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 data-testid="home-brand" className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">
              iNSTAiNSTRU
            </h1>
          </Link>
          <div className="pr-4">
            {isClient && isAuthenticated ? (
              <div className="flex items-center gap-4">
                <Link
                  href={
                    hasRole(user, RoleName.STUDENT)
                      ? '/student/lessons'
                      : isInstructorLive
                        ? '/instructor/dashboard'
                        : '/instructor/onboarding/status'
                  }
                  data-testid={hasRole(user, RoleName.STUDENT) ? 'nav-my-lessons' : undefined}
                  className="text-gray-700 hover:text-[#7E22CE] font-medium relative"
                >
                  {hasRole(user, RoleName.STUDENT)
                    ? 'My Lessons'
                    : isInstructorLive
                      ? 'My Dashboard'
                      : 'Finish Onboarding'}
                  {user?.unread_messages_count && user.unread_messages_count > 0 && (
                    <span className="absolute -top-1 -right-2 w-2 h-2 bg-red-500 rounded-full"></span>
                  )}
                </Link>
                <UserProfileDropdown />
              </div>
            ) : (
              <div className="flex items-center gap-4">
                <Link
                  href={hideStudentUi ? '/instructor/join' : '/signup?role=instructor&redirect=%2Finstructor%2Fonboarding%2Fwelcome'}
                  className="text-gray-700 hover:text-[#7E22CE] font-medium"
                >
                  Become an Instructor
                </Link>
                {!hideStudentUi && (
                  <Link
                    href="/login"
                    className="px-4 py-2 bg-[#7E22CE] text-white rounded-lg hover:bg-[#7E22CE] transition-colors font-medium"
                  >
                    Sign up / Log in
                  </Link>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Notification Bar – auth-only, reserve height when a valid session cookie exists */}
      {shouldReserveNotificationBarSpace && (
        <div className="min-h-[56px]">
          {isAuthenticated ? <NotificationBar /> : null}
        </div>
      )}

      {/* Upcoming Lessons: show only for authenticated students */}
      {isAuthenticated && !isInstructor && <UpcomingLessons />}

      {/* Hero Section */}
      <section className="py-16 relative" style={{ paddingTop: '60px' }}>
        {/* Small background image positioned to the left */}
        {heroLeftImageSrc && (
          <div
            className="absolute left-10 top-1/2 -translate-y-1/6 pointer-events-none"
            style={{ width: '400px', height: '400px' }}
            aria-hidden="true"
          >
            <div className="relative h-full w-full overflow-hidden">
              <Image
                src={heroLeftImageSrc}
                alt=""
                fill
                priority
                fetchPriority="high"
                sizes="(max-width: 1024px) 0px, 400px"
                className="object-cover"
                style={{
                  opacity: 0.7,
                  filter: 'blur(0px)',
                  contentVisibility: 'auto',
                  objectPosition: 'center',
                }}
                draggable={false}
              />
            </div>
          </div>
        )}

        {/* Small background image positioned to the right - different image */}
        {heroRightImageSrc && (
          <div
            className="absolute -right-10 top-0 pointer-events-none"
            style={{ width: '400px', height: '400px' }}
            aria-hidden="true"
          >
            <div className="relative h-full w-full overflow-hidden">
              <Image
                src={heroRightImageSrc}
                alt=""
                fill
                priority
                fetchPriority="high"
                sizes="(max-width: 1024px) 0px, 400px"
                className="object-cover"
                style={{
                  opacity: 0.7,
                  filter: 'blur(0px)',
                  contentVisibility: 'auto',
                  objectPosition: 'center',
                }}
                draggable={false}
              />
            </div>
          </div>
        )}

        <div className="relative z-10">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h1 data-testid="home-hero-title" className="text-5xl font-bold mb-8" suppressHydrationWarning aria-label="Instant Learning with iNSTAiNSTRU">
            <div className="leading-tight">
              {isClient && isAuthenticated ? (
                <span className="text-[#7E22CE]">Your Next Lesson Awaits</span>
              ) : (
                <span className="text-gray-900 dark:text-gray-100">Instant learning with</span>
              )}
            </div>
            {(!isClient || !isAuthenticated) && <div className="leading-tight text-gray-900 dark:text-gray-100">iNSTAiNSTRU</div>}
          </h1>

          {!hideStudentUi && (
          <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
            <div
              className="relative border border-[#E5E5E5] dark:border-gray-600 rounded-full focus-within:border-[#7E22CE] dark:focus-within:border-purple-400 bg-white dark:bg-gray-700 overflow-hidden"
              style={{ width: '720px', height: '64px', margin: '0 auto' }}
            >
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={
                  isClient && isAuthenticated ? 'What do you want to learn?' : 'Ready to learn something new?'
                }
                className="w-full h-full text-base bg-transparent border-none focus:outline-none text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400"
                style={{
                  padding: '0 70px 0 20px',
                  fontSize: '16px',
                }}
              />
              <button
                type="submit"
                className="absolute bg-[#FFD700] border-none rounded-full cursor-pointer flex items-center justify-center transition-all duration-200 ease-in-out hover:bg-[#FFC700] hover:scale-105"
                style={{
                  width: '52px',
                  height: '52px',
                  position: 'absolute',
                  right: '6px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  boxShadow: '0 2px 8px rgba(255, 215, 0, 0.3)',
                }}
                aria-label="Search"
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(255, 215, 0, 0.4)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(255, 215, 0, 0.3)';
                }}
              >
                <Search className="h-5 w-5 text-white" aria-hidden="true" />
              </button>
            </div>
          </form>
          )}
        </div>
        </div>
      </section>

      {/* Categories */}
      {!hideStudentUi && (
      <section className="py-2 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-2xl mx-auto">
          <div className="flex justify-center items-start space-x-10 ml-15">
            {categories.map((category) => {
              const IconComponent = category.icon;
              const isSelected = category.slug === selectedCategory;
              return (
                <div
                  key={category.slug}
                  onClick={async () => {
                    setSelectedCategory(category.slug);
                    // Clear hover on click to prevent stuck hover states
                    setHoveredCategory(null);

                    // Persist selection so Back restores it
                    if (typeof window !== 'undefined') {
                      sessionStorage.setItem('homeSelectedCategory', category.slug);
                    }

                    // Record search for category selection
                    await recordSearch(
                      {
                        query: `${category.name} lessons`,
                        search_type: SearchType.CATEGORY,
                        results_count: null,
                      },
                      isAuthenticated
                    );
                  }}
                  onMouseEnter={() => !isTouchDevice && setHoveredCategory(category.slug)}
                  onMouseLeave={() => !isTouchDevice && setHoveredCategory(null)}
                  onTouchStart={() => {
                    // For touch devices, prevent hover state
                    setHoveredCategory(null);
                  }}
                  className="group flex flex-col items-center cursor-pointer transition-colors duration-200 relative w-20 select-none"
                >
                  <IconComponent
                    size={32}
                    strokeWidth={1.5}
                    className={`mb-2 transition-colors ${
                      isSelected
                        ? 'text-gray-900 dark:text-gray-100'
                        : 'text-gray-500 group-hover:text-gray-900 dark:group-hover:text-gray-100'
                    }`}
                  />
                  <p
                    className={`text-sm font-medium mb-3 transition-colors whitespace-nowrap ${
                      isSelected
                        ? 'text-gray-900 dark:text-gray-100'
                        : 'text-gray-500 group-hover:text-gray-900 dark:group-hover:text-gray-100'
                    }`}
                  >
                    {category.name}
                  </p>
                  <p
                    className={`text-xs text-gray-500 text-center transition-opacity duration-200 h-4 flex items-center justify-center whitespace-nowrap ${
                      isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                    }`}
                  >
                    {category.subtitle || ''}
                  </p>
                  {isSelected && (
                    <div className="absolute -bottom-3 left-1/2 transform -translate-x-1/2 w-16 h-1 bg-[#FFD700] rounded-full"></div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>
      )}

      {/* Service Capsules */}
      {!hideStudentUi && (
      <section className="py-6 bg-transparent dark:bg-transparent">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex flex-wrap justify-center gap-2 min-h-[48px] items-center">
            {(() => {
              const activeCategory = hoveredCategory || selectedCategory;
              const services = activeCategory === 'kids' ? kidsServices : (categoryServices[activeCategory] || []);

              if (services.length === 0) {
                return (
                  <p className="text-sm text-gray-500 dark:text-gray-400 italic">
                    No services available for this category
                  </p>
                );
              }

              // Take first 7 services
              const servicesToShow = services.slice(0, 7);

              // Create array of all pills to render
              const pills = [];

              // Add service pills
              servicesToShow.forEach((service, index) => {
                const href =
                  activeCategory === 'kids'
                    ? `/search?service_catalog_id=${service.id}&service_name=${encodeURIComponent(service.name)}&age_group=kids&from=home`
                    : `/search?service_catalog_id=${service.id}&service_name=${encodeURIComponent(service.name)}&from=home`;
                pills.push(
                  <Link
                    key={service.id}
                    href={href}
                    onClick={async () => {
                      // Track navigation source as backup
                      if (typeof window !== 'undefined') {
                        sessionStorage.setItem('navigationFrom', '/');
                        logger.debug('Set navigation source from homepage', {
                          navigationFrom: '/',
                          serviceId: service.id,
                        });

                        // Persist current category so Back restores it
                        sessionStorage.setItem('homeSelectedCategory', activeCategory);
                      }

                      // Don't track here - let the search page track with correct results count
                    }}
                    className="group relative px-4 py-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 hover:border-gray-300 dark:hover:border-gray-500 hover:text-gray-900 dark:hover:text-white transition-all duration-200 cursor-pointer animate-fade-in-up"
                    style={{
                      animationDelay: `${index * 50}ms`,
                      animationFillMode: 'both',
                    }}
                  >
                    {service.name}
                    {/* Hover effect border */}
                    <span className="absolute inset-0 rounded-full border-2 border-transparent group-hover:border-[#FFD700] transition-all duration-200 opacity-0 group-hover:opacity-100"></span>
                  </Link>
                );
              });

              // Always add the "•••" pill as the 8th item
              pills.push(
                <Link
                  key={`more-${activeCategory}`} // Use activeCategory in key to force re-render
                  href="/services"
                  onClick={() => {
                    // Track navigation source
                    if (typeof window !== 'undefined') {
                      sessionStorage.setItem('navigationFrom', '/');
                      logger.debug('Set navigation source from homepage to services', {
                        navigationFrom: '/',
                      });
                    }
                  }}
                  className="group relative px-4 py-2 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-full text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 hover:border-gray-300 dark:hover:border-gray-500 hover:text-gray-900 dark:hover:text-white transition-all duration-200 cursor-pointer animate-fade-in-up"
                  style={{
                    animationDelay: `${7 * 50}ms`,
                    animationFillMode: 'both',
                  }}
                >
                  •••
                  {/* Hover effect border */}
                  <span className="absolute inset-0 rounded-full border-2 border-transparent group-hover:border-[#FFD700] transition-all duration-200 opacity-0 group-hover:opacity-100"></span>
                </Link>
              );

              return pills;
            })()}
          </div>
        </div>
      </section>
      )}

      {/* Book Again OR How It Works - render on client only to avoid SSR/client mismatch */}
      {shouldShowBookAgain ? (
        <BookAgain onLoadComplete={(hasHistory) => setUserHasBookingHistory(hasHistory)} />
      ) : (
        // User has no booking history OR not authenticated - show How It Works
        <section className="py-16 bg-transparent dark:bg-transparent">
          <div className="max-w-7xl mx-auto px-4">
            <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-gray-100 mb-12">
              How it works
            </h2>
            <div className="grid grid-cols-3 gap-8">
              <div className="text-center">
                <div className="text-5xl font-bold text-[#7E22CE] dark:text-purple-400 mb-4">1</div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">
                  Choose a skill
                </h3>
                <p className="text-gray-600 dark:text-gray-400">Browse or search from 100+ skills</p>
              </div>
              <div className="text-center">
                <div className="text-5xl font-bold text-[#7E22CE] dark:text-purple-400 mb-4">2</div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">
                  Schedule an instructor
                </h3>
                <p className="text-gray-600 dark:text-gray-400">Pick a time that works for you</p>
              </div>
              <div className="text-center">
                <div className="text-5xl font-bold text-[#7E22CE] dark:text-purple-400 mb-4">3</div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">Learn</h3>
                <p className="text-gray-600 dark:text-gray-400">Meet in-person and level up</p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Your Recent Searches - Only shows for authenticated users with search history (client-only) */}
      <RecentSearches />

      {/* Available Now & Trending */}
      <section className="py-16 bg-transparent dark:bg-transparent">
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid grid-cols-2 gap-8">
          {/* Available Now */}
          <div>
            <div className="flex items-center mb-6">
              <Zap className="h-6 w-6 text-[#FFD700] mr-2" />
              <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                Available Right Now
              </h2>
            </div>
            <div className="space-y-4">
              {availableNow.map((instructor, idx) => (
                <div
                  key={idx}
                  className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-[#FFFEF5] dark:hover:bg-gray-700/50 transition-colors duration-200"
                >
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                      {instructor.name}
                    </h3>
                    <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 mt-1">
                      <span>{instructor.subject}</span>
                      <span className="mx-2">•</span>
                      <span>${instructor.rate}/hr</span>
                      <span className="mx-2">•</span>
                      <Star className="h-4 w-4 text-[#FFD700] inline mr-1" />
                      <span>{instructor.rating}</span>
                    </div>
                    <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 mt-1">
                      <MapPin className="h-4 w-4 mr-1" />
                      <span>{instructor.location}</span>
                      <span className="mx-2">•</span>
                      <Clock className="h-4 w-4 mr-1" />
                      <span>Next: {instructor.nextAvailable}</span>
                    </div>
                    <button className="mt-3 w-full bg-[#7E22CE] hover:!bg-[#7E22CE] text-white hover:!text-white py-2 rounded-lg transition-colors duration-200 font-medium">
                      Book Now
                    </button>
                  </div>
                ))}
              </div>
              <Link
                href="/search?available_now=true"
                className="text-[#7E22CE] dark:text-purple-400 hover:underline mt-4 inline-block"
              >
                View All Available →
              </Link>
            </div>

            {/* Trending */}
            <div>
              <div className="flex items-center mb-6">
                <TrendingUp className="h-6 w-6 text-red-500 mr-2" />
                <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  Trending This Week
                </h2>
              </div>
              <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6">
                <ol className="space-y-3">
                  {trending.map((item, idx) => (
                    <li key={idx} className="flex justify-between items-center">
                      <span className="text-gray-900 dark:text-gray-100">
                        {idx + 1}. {item.name}
                      </span>
                      <span className="text-green-600 dark:text-green-400 text-sm">
                        ↑{item.change}%
                      </span>
                    </li>
                  ))}
                </ol>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-4">
                  Based on 2,341 bookings this week in NYC
                </p>
              </div>
              <Link
                href="/trending"
                className="text-[#7E22CE] dark:text-purple-400 hover:underline mt-4 inline-block"
              >
                Explore Trending →
              </Link>
            </div>
            </div>
          </div>
        </section>

      {/* Testimonials */}
      <section className="py-16 bg-transparent dark:bg-transparent">
        <div className="max-w-7xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-gray-100 mb-12">
            What students are saying
          </h2>
          <div className="grid grid-cols-3 gap-8">
            {testimonials.map((testimonial, idx) => (
              <div key={idx} className="bg-white dark:bg-gray-700 rounded-xl p-6">
                <p className="text-gray-900 dark:text-gray-100 italic mb-4">
                  &quot;{testimonial.quote}&quot;
                </p>
                <p className="text-gray-600 dark:text-gray-400">- {testimonial.author}</p>
                <div className="flex mt-2">
                  {[...Array(testimonial.rating)].map((_, i) => (
                    <Star key={i} className="h-5 w-5 text-[#FFD700] fill-current" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Value Props */}
      <section className="py-16">
        <div className="max-w-7xl mx-auto px-4">
          <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-gray-100 mb-12">
            The iNSTAiNSTRU difference
          </h2>
          <div className="grid grid-cols-4 gap-8">
            <div className="text-center">
              <CheckCircle className="h-12 w-12 text-green-600 dark:text-green-400 mx-auto mb-4" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Verified pros</h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">Background checked</p>
            </div>
            <div className="text-center">
              <Zap className="h-12 w-12 text-[#FFD700] mx-auto mb-4" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Instant booking
              </h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">Book in under 30 seconds</p>
            </div>
            <div className="text-center">
              <DollarSign className="h-12 w-12 text-[#7E22CE] dark:text-purple-400 mx-auto mb-4" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Fair pricing</h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                No hidden fees or surprises
              </p>
            </div>
            <div className="text-center">
              <Shield className="h-12 w-12 text-[#7E22CE] dark:text-purple-400 mx-auto mb-4" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Secure payment
              </h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">Protected by Stripe</p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-100 dark:bg-gray-800 py-12">
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid grid-cols-4 gap-8 mb-8">
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">Discover</h3>
              <ul className="space-y-2">
                <li>
                  <Link
                    href="/categories"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    All Categories
                  </Link>
                </li>
                <li>
                  <Link
                    href="/how-it-works"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    How it Works
                  </Link>
                </li>
                <li>
                  <Link
                    href="/areas"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    NYC Areas
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">Support</h3>
              <ul className="space-y-2">
                <li>
                  <Link
                    href="/help"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    Help Center
                  </Link>
                </li>
                <li>
                  <Link
                    href="/trust-safety"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    Trust & Safety
                  </Link>
                </li>
                <li>
                  <Link
                    href="/contact"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    Contact Us
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">Company</h3>
              <ul className="space-y-2">
                <li>
                  <Link
                    href="/about"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    About Us
                  </Link>
                </li>
                <li>
                  <Link
                    href="/careers"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    Careers
                  </Link>
                </li>
                <li>
                  <Link
                    href="/press"
                    className="text-gray-600 dark:text-gray-400 hover:text-[#7E22CE] dark:hover:text-purple-400"
                  >
                    Press
                  </Link>
                </li>
                <li>
                  <Link href="/terms" className={LEGAL_FOOTER_LINK_CLASSES}>
                    Terms
                  </Link>
                </li>
                <li>
                  <Link href="/privacy" className={LEGAL_FOOTER_LINK_CLASSES}>
                    Privacy
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-4">
                Download our app
              </h3>
              <div className="space-y-2">
                <button className="bg-black dark:bg-gray-700 text-white px-4 py-2 rounded-lg">
                  App Store
                </button>
                <button className="bg-black dark:bg-gray-700 text-white px-4 py-2 rounded-lg">
                  Google Play
                </button>
              </div>
            </div>
          </div>
          <div className="border-t border-gray-300 dark:border-gray-700 pt-8 flex justify-between items-center">
            <p className="text-gray-600 dark:text-gray-400">
              © {new Date().getFullYear()} {BRAND_LEGAL_NAME}
            </p>
            <div className="flex space-x-4">
              <Link
                href="#"
                className="text-[#7E22CE] dark:text-purple-400 hover:text-[#7E22CE] dark:hover:text-purple-300"
              >
                Facebook
              </Link>
              <Link
                href="#"
                className="text-[#7E22CE] dark:text-purple-400 hover:text-[#7E22CE] dark:hover:text-purple-300"
              >
                Twitter
              </Link>
              <Link
                href="#"
                className="text-[#7E22CE] dark:text-purple-400 hover:text-[#7E22CE] dark:hover:text-purple-300"
              >
                Instagram
              </Link>
            </div>
          </div>
        </div>
      </footer>

      {/* Privacy Settings Modal */}
      {showPrivacyModal && (
        <div
          className="fixed inset-0 flex items-center justify-center z-50 p-4"
          style={{ backgroundColor: 'var(--modal-backdrop)' }}
        >
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center p-4 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                Privacy Settings
              </h2>
              <button
                onClick={() => setShowPrivacyModal(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                aria-label="Close privacy settings"
              >
                <X className="h-5 w-5 text-gray-500 dark:text-gray-400" aria-hidden="true" />
              </button>
            </div>
            <div className="p-6">
              <PrivacySettings />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
