// frontend/app/dashboard/student/bookings/page.tsx
"use client";

import { BRAND } from '@/app/config/brand';
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { bookingsApi } from '@/lib/api/bookings';
import { Booking } from '@/types/booking';
import { BookingCard } from '@/components/BookingCard';

export default function MyBookingsPage() {
  const router = useRouter();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'upcoming' | 'past' | 'cancelled'>('upcoming');

  useEffect(() => {
    fetchBookings();
  }, []);

  const fetchBookings = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      // Fetch all bookings (we'll filter them client-side for tabs)
      const response = await bookingsApi.getMyBookings({
        per_page: 50 // Get more bookings to ensure we have past ones too
      });
      
      setBookings(response.bookings || []);
    } catch (err) {
      setError('Failed to load bookings. Please try again.');
      console.error('Error fetching bookings:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Filter bookings based on active tab
  const filteredBookings = bookings.filter(booking => {
    const bookingDateTime = new Date(`${booking.booking_date}T${booking.end_time}`);
    const now = new Date();
    
    switch (activeTab) {
      case 'upcoming':
        return bookingDateTime >= now && booking.status === 'CONFIRMED';
      case 'past':
        return (bookingDateTime < now && booking.status === 'CONFIRMED') || booking.status === 'COMPLETED';
      case 'cancelled':
        return booking.status === 'CANCELLED';
      default:
        return false;
    }
  });

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center">
            <Link href="/dashboard/student" className="mr-4">
              <ArrowLeft className="h-5 w-5 text-gray-600 hover:text-gray-900" />
            </Link>
            <h1 className="text-2xl font-bold text-gray-900">My Bookings</h1>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Tabs */}
        <div className="border-b border-gray-200 mb-6">
          <nav className="-mb-px flex space-x-8">
            <button
              onClick={() => setActiveTab('upcoming')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'upcoming'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Upcoming
              <span className="ml-2 text-xs">
                ({bookings.filter(b => {
                  const bookingDateTime = new Date(`${b.booking_date}T${b.end_time}`);
                  return bookingDateTime >= new Date() && b.status === 'CONFIRMED';
                }).length})
              </span>
            </button>
            <button
              onClick={() => setActiveTab('past')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'past'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Past
              <span className="ml-2 text-xs">
                ({bookings.filter(b => {
                  const bookingDateTime = new Date(`${b.booking_date}T${b.end_time}`);
                  return (bookingDateTime < new Date() && b.status === 'CONFIRMED') || b.status === 'COMPLETED';
                }).length})
              </span>
            </button>
            <button
              onClick={() => setActiveTab('cancelled')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'cancelled'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Cancelled
              <span className="ml-2 text-xs">
                ({bookings.filter(b => b.status === 'CANCELLED').length})
              </span>
            </button>
          </nav>
        </div>

        {/* Content Area */}
        <div>
          {isLoading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
              <p className="mt-2 text-gray-500">Loading bookings...</p>
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-red-600 mb-4">{error}</p>
              <button
                onClick={fetchBookings}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Try Again
              </button>
            </div>
          ) : filteredBookings.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-gray-500 text-lg">
                {activeTab === 'upcoming' && 'No upcoming bookings'}
                {activeTab === 'past' && 'No past bookings'}
                {activeTab === 'cancelled' && 'No cancelled bookings'}
              </p>
              {activeTab === 'upcoming' && (
                <Link
                  href="/instructors"
                  className="mt-4 inline-block px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                >
                  Browse Instructors
                </Link>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredBookings.map((booking) => (
                <BookingCard
                  key={booking.id}
                  booking={booking}
                  variant={activeTab === 'past' ? 'past' : 'upcoming'}
                  onCancel={() => {
                    // TODO: Implement cancel modal
                    console.log('Cancel booking:', booking.id);
                  }}
                  onComplete={() => {
                    // TODO: Implement complete functionality
                    console.log('Complete booking:', booking.id);
                  }}
                  onViewDetails={() => {
                    // TODO: Implement view details
                    console.log('View details:', booking.id);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}