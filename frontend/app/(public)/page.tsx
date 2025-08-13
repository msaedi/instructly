// frontend/app/(public)/page.tsx
'use client';

import { useState, useEffect, useRef } from 'react';
// import removed; background handled globally
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { publicApi, type TopServiceSummary } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';
import { useAuth, getUserInitials, getAvatarColor, hasRole } from '@/features/shared/hooks/useAuth';
import { RoleName, SearchType } from '@/types/enums';
import { NotificationBar } from '@/components/NotificationBar';
import { UpcomingLessons } from '@/components/UpcomingLessons';
import { BookAgain } from '@/components/BookAgain';
import { RecentSearches } from '@/components/RecentSearches';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import { convertApiResponse } from '@/lib/react-query/api';
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
  LogOut,
  Settings,
  X,
} from 'lucide-react';
import { PrivacySettings } from '@/components/PrivacySettings';
import { recordSearch } from '@/lib/searchTracking';

export default function HomePage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('sports-fitness');
  const [hoveredCategory, setHoveredCategory] = useState<string | null>(null);
  const [categoryServices, setCategoryServices] = useState<Record<string, TopServiceSummary[]>>({});
  const [isTouchDevice, setIsTouchDevice] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);
  const [userHasBookingHistory, setUserHasBookingHistory] = useState<boolean | null>(null);
  const router = useRouter();
  const { user, isAuthenticated, logout } = useAuth();
  const userMenuRef = useRef<HTMLDivElement>(null);
  const avatarRef = useRef<HTMLDivElement>(null);

  // Add React Query hook for fetching top services
  const { data: topServicesResponse } = useQuery({
    queryKey: queryKeys.services?.featured || ['services', 'featured'],
    queryFn: () => publicApi.getTopServicesPerCategory(),
    staleTime: 1000 * 60 * 60, // 1 hour - rarely changes
    gcTime: 1000 * 60 * 60 * 2, // Keep for 2 hours
  });

  const categories = [
    { icon: Music, name: 'Music', slug: 'music', subtitle: 'Instrument Voice Theory' },
    { icon: BookOpen, name: 'Tutoring', slug: 'tutoring', subtitle: 'Academic STEM Tech' },
    { icon: Dumbbell, name: 'Sports & Fitness', slug: 'sports-fitness', subtitle: '' },
    { icon: Globe, name: 'Language', slug: 'language', subtitle: '' },
    { icon: Palette, name: 'Arts', slug: 'arts', subtitle: 'Performing Visual Applied' },
    { icon: Baby, name: 'Kids', slug: 'kids', subtitle: 'Infant Toddler Preteen' },
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

  // Fetch services for all categories on mount
  useEffect(() => {
    // If React Query has already fetched the data, use it
    if (topServicesResponse) {
      if (topServicesResponse.error) {
        logger.error('API error fetching top services', new Error(topServicesResponse.error), {
          status: topServicesResponse.status,
        });
        return;
      }

      if (!topServicesResponse.data) {
        logger.error('No data received from top services endpoint');
        return;
      }

      // Map the response to our state structure
      const servicesMap: Record<string, TopServiceSummary[]> = {};

      topServicesResponse.data.categories.forEach((category) => {
        servicesMap[category.slug] = category.services;
      });

      setCategoryServices(servicesMap);

      // Log summary
      const totalServicesLoaded = Object.values(servicesMap).reduce(
        (sum, services) => sum + services.length,
        0
      );
      logger.info('All category services loaded with single request', {
        categoriesLoaded: Object.keys(servicesMap).length,
        totalServices: totalServicesLoaded,
      });
      return;
    }

    // Fallback to original fetching logic if React Query data not available
    const fetchCategoryServices = async () => {
      try {
        // Fetch all categories with their top services in a single request
        const response = await publicApi.getTopServicesPerCategory();

        if (response.error) {
          logger.error('API error fetching top services', new Error(response.error), {
            status: response.status,
          });
          return;
        }

        if (!response.data) {
          logger.error('No data received from top services endpoint');
          return;
        }

        // Map the response to our state structure
        const servicesMap: Record<string, TopServiceSummary[]> = {};

        response.data.categories.forEach((category) => {
          servicesMap[category.slug] = category.services;
        });

        setCategoryServices(servicesMap);

        // Log summary
        const totalServicesLoaded = Object.values(servicesMap).reduce(
          (sum, services) => sum + services.length,
          0
        );
        logger.info('All category services loaded with single request', {
          categoriesLoaded: Object.keys(servicesMap).length,
          totalServices: totalServicesLoaded,
        });
      } catch (error) {
        logger.error('Failed to fetch category services', error as Error);
      }
    };

    fetchCategoryServices();
  }, [topServicesResponse]);

  // Detect touch device
  useEffect(() => {
    setIsTouchDevice('ontouchstart' in window || navigator.maxTouchPoints > 0);
  }, []);

  // Background handled globally via GlobalBackground

  // Handle clicking outside of user menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        userMenuRef.current &&
        !userMenuRef.current.contains(event.target as Node) &&
        avatarRef.current &&
        !avatarRef.current.contains(event.target as Node)
      ) {
        setShowUserMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const availableNow = [
    {
      name: 'Sarah Chen',
      subject: 'Piano',
      rate: 75,
      rating: 4.9,
      location: 'Midtown',
      nextAvailable: '2:00 PM',
    },
    {
      name: 'Marcus Rodriguez',
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
    <div className="min-h-screen relative">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                iNSTAiNSTRU
              </Link>
            </div>
            <div className="flex items-center space-x-6">
              {isAuthenticated ? (
                <>
                  <Link
                    href={
                      hasRole(user, RoleName.STUDENT) ? '/student/lessons' : '/dashboard/instructor'
                    }
                    className="text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 relative"
                  >
                    My Lessons
                    {user?.unread_messages_count && user.unread_messages_count > 0 && (
                      <span className="absolute -top-1 -right-2 w-2 h-2 bg-red-500 rounded-full"></span>
                    )}
                  </Link>
                  <div className="flex items-center space-x-6">
                    <Link
                      href={
                        hasRole(user, RoleName.STUDENT)
                          ? '/dashboard/student'
                          : '/dashboard/instructor'
                      }
                      className="text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400 relative hidden md:inline-flex items-center"
                    >
                      <span>My Account</span>
                      {user?.unread_platform_messages_count &&
                        user.unread_platform_messages_count > 0 && (
                          <span className="absolute -top-1 -right-2 w-2 h-2 bg-red-500 rounded-full"></span>
                        )}
                    </Link>
                    <div ref={avatarRef} className="relative">
                      <div
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setShowUserMenu(!showUserMenu);
                        }}
                        className="w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium cursor-pointer transition-transform hover:scale-105"
                        style={{ backgroundColor: user ? getAvatarColor(user.id) : '#ccc' }}
                      >
                        {user?.profile_image_url ? (
                          <img
                            src={user.profile_image_url}
                            alt={`${user.first_name} ${user.last_name || ''}`}
                            className="w-full h-full rounded-full object-cover"
                          />
                        ) : (
                          getUserInitials(user)
                        )}
                      </div>

                      {/* Dropdown Menu */}
                      {showUserMenu && (
                        <div
                          ref={userMenuRef}
                          className="absolute right-0 top-full mt-2 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-50 animate-fade-in-down"
                        >
                          <Link
                            href={
                              hasRole(user, RoleName.STUDENT)
                                ? '/dashboard/student'
                                : '/dashboard/instructor'
                            }
                            className="block w-full px-4 py-2 text-left text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors md:hidden"
                            onClick={() => setShowUserMenu(false)}
                          >
                            My Account
                          </Link>
                          <button
                            onClick={() => {
                              setShowPrivacyModal(true);
                              setShowUserMenu(false);
                            }}
                            className="w-full px-4 py-2 text-left text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center space-x-2 transition-colors"
                          >
                            <Settings className="h-4 w-4" />
                            <span>Privacy Settings</span>
                          </button>
                          <div className="border-t border-gray-200 dark:border-gray-700 my-1"></div>
                          <button
                            onClick={() => {
                              logger.info('User logging out from dropdown menu');
                              logout();
                              setShowUserMenu(false);
                            }}
                            className="w-full px-4 py-2 text-left text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center space-x-2 transition-colors"
                          >
                            <LogOut className="h-4 w-4" />
                            <span>Log out</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <Link
                    href="/become-instructor"
                    className="text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    Become an Instructor
                  </Link>
                  <Link
                    href="/login"
                    className="px-4 py-2 border border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20"
                  >
                    Sign up / Log in
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Notification Bar */}
      <NotificationBar />

      {/* Upcoming Lessons Section */}
      <UpcomingLessons />

      {/* Hero Section */}
      <section className="py-16 relative" style={{ paddingTop: '60px' }}>
        <div className="relative z-10">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h1 className="text-5xl font-bold text-gray-900 dark:text-gray-100 mb-8">
            <div className="leading-tight">
              {isAuthenticated ? 'Your Next Lesson Awaits' : 'Instant learning with'}
            </div>
            {!isAuthenticated && <div className="leading-tight">iNSTAiNSTRU</div>}
          </h1>

          <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
            <div
              className="relative border border-[#E5E5E5] dark:border-gray-600 rounded-full focus-within:border-[#0066CC] dark:focus-within:border-blue-400 bg-white dark:bg-gray-700 overflow-hidden"
              style={{ width: '720px', height: '64px', margin: '0 auto' }}
            >
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={
                  isAuthenticated ? 'What do you want to learn?' : 'Ready to learn something new?'
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
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(255, 215, 0, 0.4)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(255, 215, 0, 0.3)';
                }}
              >
                <Search className="h-5 w-5 text-white" />
              </button>
            </div>
          </form>
        </div>
        </div>
      </section>

      {/* Categories */}
      <section className="py-6 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
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

      {/* Service Capsules */}
      <section className="py-6 bg-transparent dark:bg-transparent">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex flex-wrap justify-center gap-2 min-h-[48px] items-center">
            {(() => {
              const activeCategory = hoveredCategory || selectedCategory;
              const services = categoryServices[activeCategory] || [];

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
                pills.push(
                  <Link
                    key={service.id}
                    href={`/search?service_catalog_id=${service.id}&from=home`}
                    onClick={async () => {
                      // Track navigation source as backup
                      if (typeof window !== 'undefined') {
                        sessionStorage.setItem('navigationFrom', '/');
                        logger.debug('Set navigation source from homepage', {
                          navigationFrom: '/',
                          serviceId: service.id,
                        });
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

      {/* Book Again OR How It Works - Mutually exclusive based on booking history */}
      {isAuthenticated && userHasBookingHistory === null ? (
        // Loading state while checking booking history
        <BookAgain onLoadComplete={(hasHistory) => setUserHasBookingHistory(hasHistory)} />
      ) : isAuthenticated && userHasBookingHistory ? (
        // User has booking history - show Book Again
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
                <div className="text-5xl font-bold text-blue-600 dark:text-blue-400 mb-4">1</div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">
                  Choose a skill
                </h3>
                <p className="text-gray-600 dark:text-gray-400">
                  Browse or search from 100+ skills
                </p>
              </div>
              <div className="text-center">
                <div className="text-5xl font-bold text-blue-600 dark:text-blue-400 mb-4">2</div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">
                  Schedule an instructor
                </h3>
                <p className="text-gray-600 dark:text-gray-400">Pick a time that works for you</p>
              </div>
              <div className="text-center">
                <div className="text-5xl font-bold text-blue-600 dark:text-blue-400 mb-4">3</div>
                <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-2">Learn</h3>
                <p className="text-gray-600 dark:text-gray-400">Meet in-person and level up</p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Your Recent Searches - Only shows for authenticated users with search history */}
      <RecentSearches />

      {/* Available Now & Trending */}
      <section className="py-16 bg-transparent dark:bg-transparent">
        <div className="max-w-7xl mx-auto px-4">
          <div className="grid grid-cols-2 gap-8">
            {/* Available Now */}
            <div>
              <div className="flex items-center mb-6">
                <Zap className="h-6 w-6 text-yellow-500 mr-2" />
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
                      <Star className="h-4 w-4 text-yellow-500 inline mr-1" />
                      <span>{instructor.rating}</span>
                    </div>
                    <div className="flex items-center text-sm text-gray-600 dark:text-gray-400 mt-1">
                      <MapPin className="h-4 w-4 mr-1" />
                      <span>{instructor.location}</span>
                      <span className="mx-2">•</span>
                      <Clock className="h-4 w-4 mr-1" />
                      <span>Next: {instructor.nextAvailable}</span>
                    </div>
                    <button className="mt-3 w-full bg-[#FFD700] hover:bg-[#FFC700] text-black py-2 rounded-lg transition-colors duration-200">
                      Book Now
                    </button>
                  </div>
                ))}
              </div>
              <Link
                href="/search?available_now=true"
                className="text-blue-600 dark:text-blue-400 hover:underline mt-4 inline-block"
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
                className="text-blue-600 dark:text-blue-400 hover:underline mt-4 inline-block"
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
                  "{testimonial.quote}"
                </p>
                <p className="text-gray-600 dark:text-gray-400">- {testimonial.author}</p>
                <div className="flex mt-2">
                  {[...Array(testimonial.rating)].map((_, i) => (
                    <Star key={i} className="h-5 w-5 text-yellow-500 fill-current" />
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
              <Zap className="h-12 w-12 text-yellow-500 dark:text-yellow-400 mx-auto mb-4" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Instant booking
              </h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">Book in under 30 seconds</p>
            </div>
            <div className="text-center">
              <DollarSign className="h-12 w-12 text-blue-600 dark:text-blue-400 mx-auto mb-4" />
              <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">Fair pricing</h3>
              <p className="text-gray-600 dark:text-gray-400 text-sm">
                No hidden fees or surprises
              </p>
            </div>
            <div className="text-center">
              <Shield className="h-12 w-12 text-blue-600 dark:text-blue-400 mx-auto mb-4" />
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
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    All Categories
                  </Link>
                </li>
                <li>
                  <Link
                    href="/how-it-works"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    How it Works
                  </Link>
                </li>
                <li>
                  <Link
                    href="/areas"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
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
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    Help Center
                  </Link>
                </li>
                <li>
                  <Link
                    href="/trust-safety"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    Trust & Safety
                  </Link>
                </li>
                <li>
                  <Link
                    href="/contact"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
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
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    About Us
                  </Link>
                </li>
                <li>
                  <Link
                    href="/careers"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    Careers
                  </Link>
                </li>
                <li>
                  <Link
                    href="/press"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    Press
                  </Link>
                </li>
                <li>
                  <Link
                    href="/terms"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
                    Terms
                  </Link>
                </li>
                <li>
                  <Link
                    href="/privacy"
                    className="text-gray-600 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400"
                  >
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
            <p className="text-gray-600 dark:text-gray-400">© 2025 InstaInstru, Inc.</p>
            <div className="flex space-x-4">
              <Link
                href="#"
                className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
              >
                Facebook
              </Link>
              <Link
                href="#"
                className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
              >
                Twitter
              </Link>
              <Link
                href="#"
                className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
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
              >
                <X className="h-5 w-5 text-gray-500 dark:text-gray-400" />
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
