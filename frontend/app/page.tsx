"use client";

import { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [mounted, setMounted] = useState(false);
  
  useEffect(() => {
    setMounted(true);
    const token = localStorage.getItem('access_token');
    setIsLoggedIn(!!token);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    setIsLoggedIn(false);
    router.push('/');
  };
  const popularSearches = ["Yoga", "Piano", "Spanish", "Personal Training", "Photography", "Cooking"];
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

  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 w-full bg-white border-b border-gray-100 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link href="/" className="text-2xl font-bold text-indigo-600">
                Instructly
              </Link>
              <Link href="/instructors" className="ml-8 text-gray-600 hover:text-gray-900">
                Browse Instructors
              </Link>
            </div>
            <div className="flex items-center gap-4">
              <Link 
                href="/become-instructor"
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-full hover:bg-gray-200"
              >
                Become an Instructor
              </Link>
              {mounted && isLoggedIn ? (
                <>
                  <Link href="/dashboard" className="text-gray-600 hover:text-gray-900">
                    Dashboard
                  </Link>
                  <button 
                    onClick={handleLogout}
                    className="text-gray-600 hover:text-gray-900"
                  >
                    Log out
                  </button>
                </>
              ) : (
                <>
                  <Link href="/login" className="text-gray-600 hover:text-gray-900">
                    Sign in
                  </Link>
                  <Link 
                    href="/signup"
                    className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-full hover:bg-indigo-700"
                  >
                    Sign up
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="text-center max-w-3xl mx-auto">
          <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 mb-4 whitespace-nowrap">
            Book trusted instructors for any skill
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Learn from verified NYC experts - from yoga to music to languages
          </p>
          <div className="flex gap-2 max-w-2xl mx-auto">
            <input
              type="text"
              placeholder="What do you want to learn?"
              className="flex-1 px-4 py-3 rounded-full border border-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button className="px-6 py-3 bg-indigo-600 text-white rounded-full hover:bg-indigo-700">
              Search
            </button>
          </div>
          <div className="mt-6 flex flex-wrap gap-2 justify-center">
            {popularSearches.map((search) => (
              <button
                key={search}
                className="px-4 py-1.5 text-sm bg-gray-100 text-gray-700 rounded-full hover:bg-gray-200"
              >
                {search}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Categories Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {categories.map((category) => (
            <Link
              key={category.name}
              href={`/categories/${category.name.toLowerCase().replace(/\s+/g, '-')}`}
              className="p-6 bg-white border border-gray-200 rounded-xl hover:border-indigo-500 hover:shadow-lg transition-all"
            >
              <div className="text-3xl mb-2">{category.icon}</div>
              <h3 className="font-medium text-gray-900">{category.name}</h3>
            </Link>
          ))}
        </div>
        <div className="text-center mt-8">
          <Link href="/categories" className="text-indigo-600 hover:text-indigo-700">
            View all categories →
          </Link>
        </div>
      </section>

      {/* Why Instructly Section */}
      <section className="py-16 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="text-3xl mb-4">⚡</div>
              <h3 className="text-xl font-semibold mb-2">Instant Booking</h3>
              <p className="text-gray-600">
                Book verified instructors instantly based on real-time availability
              </p>
            </div>
            <div className="text-center">
              <div className="text-3xl mb-4">💬</div>
              <h3 className="text-xl font-semibold mb-2">Direct Communication</h3>
              <p className="text-gray-600">
                Chat with instructors before and after booking
              </p>
            </div>
            <div className="text-center">
              <div className="text-3xl mb-4">✓</div>
              <h3 className="text-xl font-semibold mb-2">Trusted Experts</h3>
              <p className="text-gray-600">
                All instructors are verified NYC professionals
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Become Instructor CTA */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto text-center">
        <h2 className="text-3xl font-bold text-gray-900 mb-4">
          Share your expertise, earn on your schedule
        </h2>
        <p className="text-gray-600 mb-8">Set your own rates and availability</p>
        <Link
          href="/become-instructor"
          className="inline-block px-8 py-3 bg-indigo-600 text-white rounded-full hover:bg-indigo-700"
        >
          Become an Instructor
        </Link>
      </section>
    </div>
  );
}
