'use client';

import Link from 'next/link';
import { useState } from 'react';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ArrowLeft, Calendar } from 'lucide-react';

import { useEmbedded } from '../_embedded/EmbeddedContext';

function BookingsPageImpl() {
  const embedded = useEmbedded();
  const [activeTab, setActiveTab] = useState<'upcoming' | 'past'>('upcoming');
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
        {/* Title card hidden when embedded; Tabs card becomes first-card anchor */}
        {!embedded && (
          <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200 relative">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
                  <Calendar className="w-6 h-6 text-[#7E22CE]" />
                </div>
                <div>
                  <h1 className="text-2xl sm:text-3xl font-bold text-gray-800">Bookings</h1>
                  <p className="text-sm text-gray-600">Upcoming and past bookings</p>
                </div>
              </div>
              <span className="hidden sm:inline" />
            </div>
          </div>
        )}

        {/* Tabs Card */}
        <div id={embedded ? 'bookings-first-card' : undefined} className="bg-white rounded-lg border border-gray-200">
          <div className="border-b border-gray-200 px-4 sm:px-6 pt-4">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setActiveTab('upcoming')}
                className={`px-2 py-2 text-xs sm:text-sm font-medium ${
                  activeTab === 'upcoming'
                    ? 'text-[#7E22CE] border-b-2 border-[#7E22CE]'
                    : 'text-gray-600 hover:text-[#7E22CE]'
                }`}
              >
                Upcoming
              </button>
              <button
                onClick={() => setActiveTab('past')}
                className={`px-2 py-2 text-xs sm:text-sm font-medium ${
                  activeTab === 'past'
                    ? 'text-[#7E22CE] border-b-2 border-[#7E22CE]'
                    : 'text-gray-600 hover:text-[#7E22CE]'
                }`}
              >
                Past
              </button>
            </div>
          </div>
          <div className="p-4 sm:p-6">
            {activeTab === 'upcoming' ? (
              <div className="text-sm text-gray-600">No upcoming bookings.</div>
            ) : (
              <div className="text-sm text-gray-600">No past bookings yet.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function InstructorBookingsPage() {
  return <BookingsPageImpl />;
}
