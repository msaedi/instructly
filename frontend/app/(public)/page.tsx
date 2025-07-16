// frontend/app/(public)/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
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
  GraduationCap,
  Sparkles,
} from 'lucide-react';

export default function HomePage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userRole, setUserRole] = useState<string | null>(null);
  const router = useRouter();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery)}`);
    }
  };

  // Check authentication on component mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      setIsAuthenticated(true);
      // Try to get user data to determine role
      fetch('http://localhost:8000/auth/me', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
        .then((response) => response.json())
        .then((userData) => {
          if (userData.role) {
            setUserRole(userData.role);
          }
        })
        .catch(() => {
          // Token might be invalid, clear it
          localStorage.removeItem('access_token');
          setIsAuthenticated(false);
        });
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setIsAuthenticated(false);
    setUserRole(null);
    router.push('/');
  };

  const categories = [
    { icon: Globe, name: 'Language', slug: 'language' },
    { icon: Music, name: 'Music', slug: 'music' },
    { icon: Dumbbell, name: 'Fitness', slug: 'fitness' },
    { icon: GraduationCap, name: 'Academics', slug: 'academics' },
    { icon: Sparkles, name: 'Hidden Gems', slug: 'other' },
  ];

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
    <div className="min-h-screen bg-white dark:bg-gray-900">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                iNSTAiNSTRU
              </Link>
            </div>
            <div className="flex items-center space-x-8">
              {isAuthenticated && (
                <Link
                  href={userRole === 'student' ? '/dashboard/student' : '/dashboard/instructor'}
                  className="text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400"
                >
                  Dashboard
                </Link>
              )}
              {!isAuthenticated && (
                <Link
                  href="/become-instructor"
                  className="text-gray-900 dark:text-gray-100 hover:text-blue-600 dark:hover:text-blue-400"
                >
                  Become an Instructor
                </Link>
              )}

              {isAuthenticated ? (
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 border border-red-600 dark:border-red-400 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  Logout
                </button>
              ) : (
                <Link
                  href="/login"
                  className="px-4 py-2 border border-blue-600 dark:border-blue-400 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20"
                >
                  Sign up / Log in
                </Link>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="py-16 bg-[#FFFEF5] dark:bg-gray-800/50" style={{ paddingTop: '60px' }}>
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h1 className="text-5xl font-bold text-gray-900 dark:text-gray-100 mb-8">
            <div className="leading-tight">Instant learning with</div>
            <div className="leading-tight">iNSTAiNSTRU</div>
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
                placeholder="Ready to learn something new?"
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
      </section>

      {/* Categories */}
      <section className="py-6 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex justify-center items-center space-x-16">
            {categories.map((category, index) => {
              const IconComponent = category.icon;
              return (
                <Link
                  key={category.slug}
                  href={`/search?category=${category.slug}`}
                  className={`group flex flex-col items-center cursor-pointer transition-colors duration-200 relative`}
                >
                  <IconComponent
                    size={32}
                    strokeWidth={1.5}
                    className={
                      index === 2 ? 'text-gray-900 dark:text-gray-100 mb-2' : 'text-gray-500 mb-2'
                    }
                  />
                  <p
                    className={`text-sm font-medium ${
                      index === 2 ? 'text-gray-900 dark:text-gray-100' : 'text-gray-500'
                    }`}
                  >
                    {category.name}
                  </p>
                  {index === 2 && (
                    <div className="absolute -bottom-3 left-1/2 transform -translate-x-1/2 w-16 h-1 bg-[#FFD700] rounded-full"></div>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      {/* Subcategories */}
      <section className="py-6 bg-[#FFFEF5] dark:bg-gray-800/50">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex flex-wrap justify-center gap-3">
            {['Yoga', 'Personal Training', 'Pilates', 'Martial Arts', 'Dance', 'Nutrition'].map(
              (subcategory) => (
                <Link
                  key={subcategory}
                  href={`/search?subcategory=${subcategory.toLowerCase().replace(' ', '-')}`}
                  className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-full text-sm text-gray-600 dark:text-gray-400 hover:border-[#FFD700] dark:hover:border-[#FFD700] hover:text-black dark:hover:text-white transition-colors duration-200"
                >
                  {subcategory}
                </Link>
              )
            )}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-16 bg-gray-50 dark:bg-gray-800">
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
              <p className="text-gray-600 dark:text-gray-400">Browse or search from 100+ skills</p>
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

      {/* Available Now & Trending */}
      <section className="py-16 bg-[#FFFEF5] dark:bg-gray-800/50">
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
      <section className="py-16 bg-gray-50 dark:bg-gray-800">
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
    </div>
  );
}
