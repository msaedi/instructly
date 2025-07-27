// frontend/components/BookAgain.tsx
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Star } from 'lucide-react';
import { bookingsApi } from '@/lib/api/bookings';
import { Booking } from '@/types/booking';
import { logger } from '@/lib/logger';
import { useAuth } from '@/features/shared/hooks/useAuth';

interface UniqueInstructor {
  instructorId: number;
  instructorName: string;
  serviceName: string;
  serviceId: number;
  hourlyRate: number;
  rating?: number;
  lastBookingDate: string;
}

interface BookAgainProps {
  onLoadComplete?: (hasHistory: boolean) => void;
}

export function BookAgain({ onLoadComplete }: BookAgainProps) {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [uniqueInstructors, setUniqueInstructors] = useState<UniqueInstructor[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasBookingHistory, setHasBookingHistory] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      fetchBookingHistory();
    }
  }, [isAuthenticated]);

  const fetchBookingHistory = async () => {
    try {
      logger.debug('Fetching booking history for Book Again section');

      // Fetch past bookings (completed ones)
      const response = await bookingsApi.getMyBookings({
        status: 'COMPLETED',
        per_page: 50, // Get more to ensure we find 3 unique instructors
      });

      if (response.bookings && response.bookings.length > 0) {
        // Extract unique instructors
        const instructorMap = new Map<number, UniqueInstructor>();

        response.bookings.forEach((booking: Booking) => {
          if (booking.instructor && !instructorMap.has(booking.instructor.id)) {
            instructorMap.set(booking.instructor.id, {
              instructorId: booking.instructor.id,
              instructorName: booking.instructor.full_name,
              serviceName: booking.service_name,
              serviceId: booking.id, // Using booking ID as we don't have instructor_service_id
              hourlyRate: booking.hourly_rate,
              rating: 4.8, // TODO: Get actual rating from instructor profile
              lastBookingDate: booking.booking_date,
            });
          }
        });

        // Get the first 3 unique instructors
        const uniqueList = Array.from(instructorMap.values()).slice(0, 3);
        setUniqueInstructors(uniqueList);
        setHasBookingHistory(uniqueList.length > 0);

        logger.info('Book Again section loaded', {
          totalBookings: response.bookings.length,
          uniqueInstructors: uniqueList.length,
        });
      } else {
        setHasBookingHistory(false);
      }
    } catch (error) {
      logger.error('Error fetching booking history', error);
      setHasBookingHistory(false);
    } finally {
      setIsLoading(false);
    }
  };

  // Notify parent component when loading is complete
  useEffect(() => {
    if (!isLoading && onLoadComplete) {
      onLoadComplete(hasBookingHistory);
    }
  }, [isLoading, hasBookingHistory, onLoadComplete]);

  const handleBookAgain = (instructor: UniqueInstructor) => {
    logger.debug('Book Again clicked', {
      instructorId: instructor.instructorId,
      serviceName: instructor.serviceName,
    });

    // Navigate to instructor profile with calendar modal open
    // Adding a query param to signal that calendar should open
    router.push(
      `/instructors/${instructor.instructorId}?openCalendar=true&serviceId=${instructor.serviceId}`
    );
  };

  // Don't render anything if not authenticated or still loading
  if (!isAuthenticated || isLoading) {
    return null;
  }

  // Return loading state or null if no booking history
  if (!hasBookingHistory) {
    return null;
  }

  // Show Book Again section
  return (
    <section className="py-16 bg-gray-50 dark:bg-gray-800">
      <div className="max-w-7xl mx-auto px-4">
        <h2 className="text-3xl font-bold text-center text-gray-900 dark:text-gray-100 mb-12">
          Book Again
        </h2>

        {/* Desktop: Grid, Mobile: Horizontal scroll */}
        <div className="block md:grid md:grid-cols-3 md:gap-6 overflow-x-auto md:overflow-visible">
          <div className="flex md:contents gap-4 md:gap-0">
            {uniqueInstructors.map((instructor, idx) => (
              <div
                key={instructor.instructorId}
                className="flex-shrink-0 w-80 md:w-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-6 hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => handleBookAgain(instructor)}
              >
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
                  {instructor.serviceName}
                </h3>
                <p className="text-gray-600 dark:text-gray-400 mb-2">
                  with {instructor.instructorName}
                </p>
                <div className="flex items-center mb-2">
                  <Star className="h-4 w-4 text-yellow-500 fill-current mr-1" />
                  <span className="text-gray-900 dark:text-gray-100">
                    {instructor.rating || '4.8'}
                  </span>
                </div>
                <p className="text-gray-900 dark:text-gray-100 font-semibold mb-4">
                  ${instructor.hourlyRate}/hour
                </p>
                <button
                  className="w-full bg-[#FFD700] hover:bg-[#FFC700] text-black py-2 rounded-lg font-medium transition-colors"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleBookAgain(instructor);
                  }}
                >
                  Book Again
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Mobile scroll indicator */}
        <div className="flex justify-center mt-4 space-x-2 md:hidden">
          {uniqueInstructors.map((_, idx) => (
            <div key={idx} className="w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600" />
          ))}
        </div>
      </div>
    </section>
  );
}
