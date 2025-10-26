'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ArrowLeft, ChevronDown, Star } from 'lucide-react';

export default function InstructorReviewsPage(props?: { embedded?: boolean }) {
  const embedded = Boolean(props?.embedded);
  const [filter, setFilter] = useState<'all' | 5 | 4 | 3 | 2 | 1>('all');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement | null>(null);
  const [hoveredOpt, setHoveredOpt] = useState<'all' | 5 | 4 | 3 | 2 | 1 | null>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!filterRef.current) return;
      if (!filterRef.current.contains(e.target as Node)) setIsFilterOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const filterLabel = filter === 'all' ? 'All reviews' : `${filter} stars`;
  return (
    <div className="min-h-screen">
      {/* Header hidden when embedded */}
      {!embedded && (
        <header className="relative bg-white backdrop-blur-sm border-b border-gray-200 px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-0 sm:pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 hidden sm:block">
            <div className="container mx-auto px-8 lg:px-32 max-w-6xl pointer-events-none">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE] pointer-events-auto">
                <ArrowLeft className="w-4 h-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'max-w-none px-0 lg:px-0 py-0' : 'container mx-auto px-8 lg:px-32 py-8 max-w-6xl'}>
        {!embedded && (
          <div className="sm:hidden mb-2">
            <Link href="/instructor/dashboard" aria-label="Back to dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
              <ArrowLeft className="w-5 h-5" />
              <span className="sr-only">Back to dashboard</span>
            </Link>
          </div>
        )}
        {/* Title card hidden when embedded; Ratings card is first anchor */}
        {!embedded && (
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                <Star className="w-6 h-6 text-[#7E22CE]" />
              </div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-800">Reviews</h1>
                <p className="text-sm text-gray-600">Student ratings and feedback</p>
              </div>
            </div>
            <Link href="/instructor/dashboard" className="text-[#7E22CE] sm:hidden">Dashboard</Link>
          </div>
        </div>
        )}

        {/* Ratings summary */}
        <div id={embedded ? 'reviews-first-card' : undefined} className="bg-white rounded-lg p-6 border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-gray-900">0 Reviews</h2>
            <span className="text-gray-900 font-semibold">0</span>
          </div>

          <ul className="space-y-4">
            {[5,4,3,2,1].map((stars) => (
              <li
                key={stars}
                className={`grid grid-cols-[auto_1fr_auto] items-center gap-3 ${filter !== 'all' && filter !== stars ? 'opacity-60' : ''}`}
              >
                <span className="text-[#7E22CE] font-medium">{stars} stars</span>
                <div className="h-3 rounded-full bg-gray-200">
                  <div className="h-3 rounded-full bg-gray-300" style={{ width: '0%' }} />
                </div>
                <span className="text-gray-900 font-medium">0</span>
              </li>
            ))}
          </ul>

          <div className="mt-6 relative" ref={filterRef}>
            <button
              type="button"
              onClick={() => setIsFilterOpen((v) => !v)}
              className="inline-flex items-center gap-1 text-[#7E22CE] font-semibold hover:text-[#5f1aa4]"
              aria-haspopup="listbox"
              aria-expanded={isFilterOpen}
            >
              <span>{filterLabel}</span>
              <ChevronDown className={`w-4 h-4 transition-transform ${isFilterOpen ? 'rotate-180' : ''}`} />
            </button>
            {isFilterOpen && (
              <ul
                role="listbox"
                className="absolute z-10 mt-2 w-44 rounded-md border border-gray-200 bg-white shadow-md p-1"
              >
                {(['all', 5, 4, 3, 2, 1] as const).map((opt) => (
                  <li key={String(opt)}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={filter === opt}
                      onClick={() => { setFilter(opt); setIsFilterOpen(false); }}
                      onMouseEnter={() => setHoveredOpt(opt)}
                      onMouseLeave={() => setHoveredOpt((h) => (h === opt ? null : h))}
                      className={`w-full text-left px-3 py-2 rounded-md transition-colors cursor-pointer ${
                        hoveredOpt === opt ? 'bg-purple-50 text-[#7E22CE]' : ''
                      } ${
                        filter === opt ? 'bg-purple-100 text-[#7E22CE] font-semibold' : 'text-gray-800'
                      }`}
                    >
                      {opt === 'all' ? 'All reviews' : `${opt} stars`}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="mt-8 space-y-3">
            <p className="text-gray-500 text-lg">You don’t have any reviews yet — but you’re just getting started!</p>
            <p className="text-gray-500 text-lg">Happy students leave great feedback. After each lesson, kindly remind them to rate their experience.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
