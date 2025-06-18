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
import { CancelBookingModal } from '@/components/modals/CancelBookingModal';
import BookingDetailsModal from '@/components/BookingDetailsModal';
import { logger } from '@/lib/logger';

/**
 * MyBookingsPage Component
 * 
 * Main booking management interface for students. Displays all bookings
 * organized into tabs (upcoming, past, cancelled) with actions for each.
 * 
 * Features:
 * - Tabbed interface for booking organization
 * - Real-time booking counts per tab
 * - Cancel booking functionality with confirmation modal
 * - View detailed booking information
 * - Automatic sorting by date and status
 * - Loading and error states
 * - Empty state with CTA to browse instructors
 * 
 * @component
 * @example
 * ```tsx
 * // This is a page component, typically accessed via routing
 * // Route: /dashboard/student/bookings
 * ```
 */
export default function MyBookingsPage() {
  const router = useRouter();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'upcoming' | 'past' | 'cancelled'>('upcoming');
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);

  useEffect(() => {
    logger.info('Student bookings page loaded');
    fetchBookings();
  }, []);

  /**
   * Fetch all bookings for the current student
   * Client-side filtering is used for tab organization
   */
  const fetchBookings = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      logger.info('Fetching student bookings');
      
      // Fetch all bookings (we'll filter them client-side for tabs)
      const response = await bookingsApi.getMyBookings({
        per_page: 50 // Get more bookings to ensure we have past ones too
      });
      
      const bookingCount = response.bookings?.length || 0;
      logger.info('Bookings fetched successfully', { 
        count: bookingCount,
        hasBookings: bookingCount > 0
      });
      
      setBookings(response.bookings || []);
    } catch (err) {
      const errorMessage = 'Failed to load bookings. Please try again.';
      logger.error('Error fetching bookings', err);
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Handle booking cancellation with reason
   * @param reason - The cancellation reason provided by the student
   */
  const handleCancelBooking = async (reason: string) => {
    if (!selectedBooking) {
      logger.warn('Attempted to cancel booking without selection');
      return;
    }
    
    setCancelError(null); // Clear any previous errors
    
    logger.info('Cancelling booking', { 
      bookingId: selectedBooking.id,
      hasReason: !!reason 
    });
  
    try {
      await bookingsApi.cancelBooking(selectedBooking.id, {
        cancellation_reason: reason
      });
      
      logger.info('Booking cancelled successfully', { 
        bookingId: selectedBooking.id 
      });
  
      // Refresh bookings after successful cancellation
      await fetchBookings();
      setShowCancelModal(false);
      setSelectedBooking(null);
    } catch (err) {
      // Set error message to display in modal
      const errorMessage = err instanceof Error ? err.message : 'Failed to cancel booking. Please try again.';
      logger.error('Failed to cancel booking', err, { 
        bookingId: selectedBooking.id 
      });
      setCancelError(errorMessage);
      
      // Don't close the modal on error so user can see the message and retry
    }
  };

  /**
   * Open the cancellation modal for a specific booking
   * @param booking - The booking to cancel
   */
  const openCancelModal = (booking: Booking) => {
    logger.debug('Opening cancel modal', { 
      bookingId: booking.id,
      status: booking.status 
    });
    setSelectedBooking(booking);
    setShowCancelModal(true);
  };

  /**
   * Filter bookings based on active tab
   * - Upcoming: Future bookings with CONFIRMED status
   * - Past: Past bookings (CONFIRMED or COMPLETED)
   * - Cancelled: Bookings with CANCELLED status
   */
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

  /**
   * Get count of bookings for a specific tab
   * @param tab - The tab to count bookings for
   */
  const getTabCount = (tab: 'upcoming' | 'past' | 'cancelled'): number => {
    return bookings.filter(b => {
      const bookingDateTime = new Date(`${b.booking_date}T${b.end_time}`);
      const now = new Date();
      
      switch (tab) {
        case 'upcoming':
          return bookingDateTime >= now && b.status === 'CONFIRMED';
        case 'past':
          return (bookingDateTime < now && b.status === 'CONFIRMED') || b.status === 'COMPLETED';
        case 'cancelled':
          return b.status === 'CANCELLED';
        default:
          return false;
      }
    }).length;
  };

  /**
   * Handle tab change
   * @param tab - The tab to switch to
   */
  const handleTabChange = (tab: 'upcoming' | 'past' | 'cancelled') => {
    logger.debug('Switching tab', { 
      from: activeTab, 
      to: tab,
      count: getTabCount(tab)
    });
    setActiveTab(tab);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center">
            <Link 
              href="/dashboard/student" 
              className="mr-4"
              onClick={() => logger.debug('Navigating back to student dashboard')}
            >
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
          <nav className="-mb-px flex space-x-8" role="tablist">
            <button
              onClick={() => handleTabChange('upcoming')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'upcoming'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
              role="tab"
              aria-selected={activeTab === 'upcoming'}
              aria-controls="upcoming-panel"
            >
              Upcoming
              <span className="ml-2 text-xs">
                ({getTabCount('upcoming')})
              </span>
            </button>
            <button
              onClick={() => handleTabChange('past')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'past'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
              role="tab"
              aria-selected={activeTab === 'past'}
              aria-controls="past-panel"
            >
              Past
              <span className="ml-2 text-xs">
                ({getTabCount('past')})
              </span>
            </button>
            <button
              onClick={() => handleTabChange('cancelled')}
              className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'cancelled'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
              role="tab"
              aria-selected={activeTab === 'cancelled'}
              aria-controls="cancelled-panel"
            >
              Cancelled
              <span className="ml-2 text-xs">
                ({getTabCount('cancelled')})
              </span>
            </button>
          </nav>
        </div>

        {/* Content Area */}
        <div role="tabpanel" id={`${activeTab}-panel`}>
          {isLoading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
              <p className="mt-2 text-gray-500">Loading bookings...</p>
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-red-600 mb-4">{error}</p>
              <button
                onClick={() => {
                  logger.info('Retrying bookings fetch after error');
                  fetchBookings();
                }}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
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
                  className="mt-4 inline-block px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                  onClick={() => logger.debug('Navigating to browse instructors from empty state')}
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
                  onCancel={() => openCancelModal(booking)}
                  onComplete={() => {
                    // TODO: Implement complete functionality
                    logger.info('Complete booking clicked', { 
                      bookingId: booking.id 
                    });
                  }}
                  onViewDetails={() => {
                    logger.debug('Opening booking details modal', { 
                      bookingId: booking.id 
                    });
                    setSelectedBooking(booking);
                    setShowDetailsModal(true);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Cancel Modal */}
      <CancelBookingModal
        booking={selectedBooking}
        isOpen={showCancelModal}
        error={cancelError}
        onClose={() => {
          logger.debug('Closing cancel modal');
          setShowCancelModal(false);
          setSelectedBooking(null);
          setCancelError(null); // Clear error when closing
        }}
        onConfirm={handleCancelBooking}
      />
      
      {/* Booking Details Modal */}
      <BookingDetailsModal
        booking={selectedBooking}
        isOpen={showDetailsModal}
        onClose={() => {
          logger.debug('Closing booking details modal');
          setShowDetailsModal(false);
          setSelectedBooking(null);
        }}
      />
    </div>
  );
}