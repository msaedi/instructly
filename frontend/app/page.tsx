// frontend/app/page.tsx
"use client";

import { BRAND } from '@/app/config/brand'
import { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { logger } from '@/lib/logger';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import type { UserData } from '@/types/user';
import { isInstructorUser } from '@/types/user';

/**
 * Home Page Component
 * 
 * Main landing page for InstaInstru platform. Serves as the entry point
 * for both students looking for instructors and instructors wanting to join.
 * 
 * Features:
 * - Dynamic navigation based on authentication status
 * - Search functionality with popular searches
 * - Category browsing with emoji icons
 * - Value propositions (instant booking, direct communication, trusted experts)
 * - Call-to-action for becoming an instructor (hidden for existing instructors)
 * - Responsive design with mobile-first approach
 * 
 * @component
 * @example
 * ```tsx
 * // This is the root page component
 * // Accessed via: /
 * ```
 */
export default function Home() {
  const router = useRouter();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isInstructor, setIsInstructor] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  
  // Popular searches for quick access
  const popularSearches = ["Yoga", "Piano", "Spanish", "Personal Training", "Photography", "Cooking"];
  
  // Main service categories with emoji icons
  const categories = [
    { name: "Fitness & Yoga", icon: "💪" },
    { name: "Music", icon: "🎵" },
    { name: "Languages", icon: "🗣️" },
    { name: "Arts & Crafts", icon: "🎨" },
    { name: "Cooking", icon: "👨‍🍳" },
    { name: "Academic Tutoring", icon: "📚" },
    { name: "Dance", icon: "💃" },
    { name: "Photography", icon: "📸" },
  ];
  
  useEffect(() => {
    setMounted(true);
    const token = localStorage.getItem('access_token');
    setIsLoggedIn(!!token);
    
    logger.info('Home page loaded', { 
      isAuthenticated: !!token,
      referrer: document.referrer || 'direct'
    });

    // Check if user is an instructor
    const checkUserRole = async () => {
      if (token) {
        try {
          const response = await fetchWithAuth(API_ENDPOINTS.ME);
          if (response.ok) {
            const userData: UserData = await response.json();
            const instructorStatus = isInstructorUser(userData);
            setIsInstructor(instructorStatus);
            logger.debug('User role checked on home page', { 
              isInstructor: instructorStatus,
              userId: userData.id 
            });
          }
        } catch (error) {
          logger.error('Failed to check user role on home page', error);
        }
      }
    };

    checkUserRole();
  }, []);

  /**
   * Handle user logout
   * Clears authentication and refreshes page
   */
  const handleLogout = () => {
    logger.info('User logging out from home page');
    localStorage.removeItem('access_token');
    setIsLoggedIn(false);
    setIsInstructor(false);
    router.push('/');
  };

  /**
   * Handle search submission
   * @param e - Form event
   */
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!searchQuery.trim()) {
      logger.debug('Empty search attempted');
      return;
    }
    
    logger.info('Search initiated from home page', { 
      query: searchQuery,
      queryLength: searchQuery.length 
    });
    
    // TODO: Implement search functionality
    // For now, redirect to instructors page with search query
    router.push(`/instructors?search=${encodeURIComponent(searchQuery)}`);
  };

  /**
   * Handle popular search click
   * @param search - The search term clicked
   */
  const handlePopularSearchClick = (search: string) => {
    logger.debug('Popular search clicked', { search });
    setSearchQuery(search);
    // TODO: Trigger search or redirect
    router.push(`/instructors?search=${encodeURIComponent(search)}`);
  };

  /**
   * Handle category click
   * @param category - The category clicked
   */
  const handleCategoryClick = (category: { name: string; icon: string }) => {
    logger.debug('Category clicked', { 
      category: category.name,
      icon: category.icon 
    });
    // Navigation handled by Link component
  };

  return (
    <div className="min-h-screen bg-white dark:bg-gray-900">
      {/* Navigation */}
      <nav className="fixed top-0 w-full bg-white dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link 
                href="/" 
                className="text-2xl font-bold text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
              >
                {BRAND.name}
              </Link>
              <Link 
                href="/instructors" 
                className="ml-8 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
                onClick={() => logger.debug('Navigating to browse instructors')}
              >
                Browse Instructors
              </Link>
            </div>
            <div className="flex items-center gap-4">
              {/* Conditionally show "Become an Instructor" only for non-instructors */}
              {!isInstructor && (
                <Link 
                  href="/become-instructor"
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                  onClick={() => logger.debug('Navigating to become instructor')}
                >
                  Become an Instructor
                </Link>
              )}
              {mounted && isLoggedIn ? (
                <>
                  <Link 
                    href="/dashboard" 
                    className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
                    onClick={() => logger.debug('Navigating to dashboard from home')}
                  >
                    Dashboard
                  </Link>
                  <button 
                    onClick={handleLogout}
                    className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
                  >
                    Log out
                  </button>
                </>
              ) : (
                <Link 
                  href="/login" 
                  className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-full hover:bg-indigo-700 transition-colors"
                  onClick={() => logger.debug('Navigating to login from home')}
                >
                  Sign up / Log in
                </Link>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="text-center max-w-3xl mx-auto">
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 dark:text-white mb-4 whitespace-nowrap">
            Book trusted instructors for any skill
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400 mb-8">
            Learn from verified NYC experts - from yoga to music to languages
          </p>
          
          {/* Search Form */}
          <form onSubmit={handleSearch} className="flex gap-2 max-w-2xl mx-auto">
            <input
              type="text"
              placeholder="What do you want to learn?"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="flex-1 px-4 py-3 rounded-full border border-gray-300 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:bg-gray-800 dark:text-white"
              aria-label="Search for skills or instructors"
            />
            <button 
              type="submit"
              className="px-6 py-3 bg-indigo-600 text-white rounded-full hover:bg-indigo-700 transition-colors"
              aria-label="Search"
            >
              Search
            </button>
          </form>
          
          {/* Popular Searches */}
          <div className="mt-6 flex flex-wrap gap-2 justify-center">
            {popularSearches.map((search) => (
              <button
                key={search}
                onClick={() => handlePopularSearchClick(search)}
                className="px-4 py-1.5 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                aria-label={`Search for ${search}`}
              >
                {search}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Categories Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <h2 className="sr-only">Browse by Category</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {categories.map((category) => (
            <Link
              key={category.name}
              href={`/categories/${category.name.toLowerCase().replace(/\s+/g, '-')}`}
              className="p-6 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl hover:border-indigo-500 dark:hover:border-indigo-400 hover:shadow-lg transition-all"
              onClick={() => handleCategoryClick(category)}
              aria-label={`Browse ${category.name} instructors`}
            >
              <div className="text-3xl mb-2" aria-hidden="true">{category.icon}</div>
              <h3 className="font-medium text-gray-900 dark:text-white">{category.name}</h3>
            </Link>
          ))}
        </div>
        <div className="text-center mt-8">
          <Link 
            href="/categories" 
            className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 transition-colors"
            onClick={() => logger.debug('Navigating to all categories')}
          >
            View all categories →
          </Link>
        </div>
      </section>

      {/* Why {BRAND.name} Section */}
      <section className="py-16 bg-gray-50 dark:bg-gray-800" aria-labelledby="why-instainstru">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 id="why-instainstru" className="sr-only">Why Choose {BRAND.name}</h2>
          <div className="grid md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="text-3xl mb-4" aria-hidden="true">⚡</div>
              <h3 className="text-xl font-semibold mb-2 dark:text-white">Instant Booking</h3>
              <p className="text-gray-600 dark:text-gray-400">
                Book verified instructors instantly based on real-time availability
              </p>
            </div>
            <div className="text-center">
              <div className="text-3xl mb-4" aria-hidden="true">💬</div>
              <h3 className="text-xl font-semibold mb-2 dark:text-white">Direct Communication</h3>
              <p className="text-gray-600 dark:text-gray-400">
                Chat with instructors before and after booking
              </p>
            </div>
            <div className="text-center">
              <div className="text-3xl mb-4" aria-hidden="true">✓</div>
              <h3 className="text-xl font-semibold mb-2 dark:text-white">Trusted Experts</h3>
              <p className="text-gray-600 dark:text-gray-400">
                All instructors are verified NYC professionals
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Become Instructor CTA - Only show for non-instructors */}
      {!isInstructor && (
        <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-4">
            Share your expertise, earn on your schedule
          </h2>
          <p className="text-gray-600 dark:text-gray-400 mb-8">Set your own rates and availability</p>
          <Link
            href="/become-instructor"
            className="inline-block px-8 py-3 bg-indigo-600 text-white rounded-full hover:bg-indigo-700 transition-colors"
            onClick={() => {
              logger.info('Become instructor CTA clicked from home page');
            }}
          >
            Become an Instructor
          </Link>
        </section>
      )}
    </div>
  );
}