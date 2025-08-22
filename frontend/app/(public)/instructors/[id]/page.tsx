'use client';
// frontend/app/(public)/instructors/[id]/page.tsx

import { Suspense, useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Heart } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { logger } from '@/lib/logger';
import { InstructorHeader } from '@/features/instructor-profile/components/InstructorHeader';
import { ServiceCards } from '@/features/instructor-profile/components/ServiceCards';
import { AvailabilityCalendar } from '@/features/instructor-profile/components/AvailabilityCalendar';
import { ReviewsSection } from '@/features/instructor-profile/components/ReviewsSection';
import { BookingButton } from '@/features/instructor-profile/components/BookingButton';
import { InstructorProfileSkeleton } from '@/features/instructor-profile/components/InstructorProfileSkeleton';
import { AvailabilityGrid } from '@/features/instructor-profile/components/AvailabilityGrid';
import { useInstructorProfile } from '@/features/instructor-profile/hooks/useInstructorProfile';
import { useSaveInstructor } from '@/features/instructor-profile/hooks/useSaveInstructor';
import { useBookingModal } from '@/features/instructor-profile/hooks/useBookingModal';
import { useInstructorAvailability } from '@/features/instructor-profile/hooks/useInstructorAvailability';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import { useRouter as useNextRouter } from 'next/navigation';
import { calculateEndTime } from '@/features/student/booking/hooks/useCreateBooking';
import {
  BookingPayment,
  BookingType,
  determineBookingType,
  calculateServiceFee,
  calculateTotalAmount,
} from '@/features/student/payment';
import { navigationStateManager } from '@/lib/navigation/navigationStateManager';
import { format } from 'date-fns';
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';
import UserProfileDropdown from '@/components/UserProfileDropdown';

// Booking intent helpers
function storeBookingIntent(bookingIntent: {
  instructorId: string;
  serviceId?: string;
  date: string;
  time: string;
  duration: number;
  skipModal?: boolean;
}) {
  try {
    sessionStorage.setItem('bookingIntent', JSON.stringify(bookingIntent));
  } catch (err) {
    // Silent failure
  }
}

function getBookingIntent(): {
  instructorId: string;
  serviceId?: string;
  date: string;
  time: string;
  duration: number;
  skipModal?: boolean;
} | null {
  try {
    const stored = sessionStorage.getItem('bookingIntent');
    if (stored) {
      return JSON.parse(stored);
    }
  } catch (err) {
    // Silent failure
  }
  return null;
}

function clearBookingIntent() {
  try {
    sessionStorage.removeItem('bookingIntent');
  } catch (err) {
    // Silent failure
  }
}

function InstructorProfileContent() {
  const params = useParams();
  const router = useRouter();
  const nextRouter = useNextRouter();
  const instructorId = params.id as string;
  const [selectedSlot, setSelectedSlot] = useState<{ date: string; time: string; duration: number; availableDuration?: number } | null>(null);
  const [isSlotUserSelected, setIsSlotUserSelected] = useState(false); // Track if slot was manually selected by user
  const [weekStart, setWeekStart] = useState<Date | null>(null);
  const [hasRestoredIntent, setHasRestoredIntent] = useState(false);

  const { data: instructor, isLoading, error, refetch, isFetching } = useInstructorProfile(instructorId);
  const [rateSecs, setRateSecs] = useState<number | null>(null);
  const { setActivity } = useBackgroundConfig();
  // Detect rate limit errors and auto-retry once with a friendly inline banner
  useEffect(() => {
    if (!error) return;
    const message = (error as any)?.message || '';
    const isRateLimited = /hamsters|Too Many Requests|rate limit/i.test(message);
    if (!isRateLimited) return;
    const m = message.match(/(\d+)s/);
    const seconds = m ? parseInt(m[1], 10) : 3;
    setRateSecs(seconds);
    const interval = setInterval(() => {
      setRateSecs((prev) => {
        if (prev === null) return prev;
        if (prev <= 1) {
          clearInterval(interval);
          refetch();
          return null;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [error, refetch]);

  const RateLimitBanner = () => (
    rateSecs !== null ? (
      <div className="container mx-auto px-4 max-w-6xl">
        <div className="mb-4 rounded-md bg-yellow-50 border border-yellow-200 text-yellow-900 px-3 py-2 text-sm">
          Our hamsters are sprinting. Give them {rateSecs}s.
        </div>
      </div>
    ) : null
  );


  // Set background activity based on the service the user likely arrived for
  useEffect(() => {
    if (!instructor) return;
    // Use the first service's skill as the activity identifier
    const primaryService = instructor.services?.[0]?.skill || '';
    if (primaryService) {
      setActivity(primaryService.toLowerCase());
    }
    // Do not clear on unmount here to allow navigation within profile without flicker
  }, [instructor, setActivity]);
  // IMPORTANT: Use the canonical instructor.id (user_id ULID) when available to avoid duplicate queries
  // Defer availability fetch until canonical id is known to avoid duplicate requests
  const availabilityInstructorId = instructor?.id || '';
  const { data: availability } = useInstructorAvailability(
    availabilityInstructorId,
    weekStart ? format(weekStart, 'yyyy-MM-dd') : undefined
  );
  const { isSaved, toggleSave, isLoading: isSaveLoading } = useSaveInstructor(
    instructor?.id || ''
  );
  const bookingModal = useBookingModal();

  // Helper function to handle booking - checks auth and redirects if needed
  const handleBookingClick = (service?: any, serviceDuration?: number) => {
    const token = localStorage.getItem('access_token');
    const selectedService = service || instructor?.services[0]; // Use provided service or default to first
    const duration = serviceDuration || 60; // Use provided duration or default

    // If no slot is selected OR slot was auto-selected (not user-selected), open the booking modal
    if (!selectedSlot || !isSlotUserSelected) {
      if (!token) {
        // User not authenticated - redirect to login first
        const returnUrl = `/instructors/${instructor?.user_id}`;
        nextRouter.push(`/login?redirect=${encodeURIComponent(returnUrl)}`);
        return;
      }
      // Open booking modal for time slot selection
      bookingModal.openBookingModal({
        date: '', // Will be selected in modal
        time: '', // Will be selected in modal
        duration,
      });
      return;
    }

    if (selectedSlot && selectedService && instructor) {
      const bookingDate = new Date(selectedSlot.date + 'T' + selectedSlot.time);
      const hourlyRate = selectedService.hourly_rate;
      const totalPrice = hourlyRate * (duration / 60);
      const basePrice = totalPrice;
      const serviceFee = calculateServiceFee(basePrice);
      const totalAmount = calculateTotalAmount(basePrice);
      const bookingType = determineBookingType(bookingDate);

      const paymentBookingData: BookingPayment = {
        bookingId: '',
        instructorId: String(instructor.user_id),
        instructorName: instructor.user ? `${instructor.user.first_name} ${instructor.user.last_initial ? instructor.user.last_initial + '.' : ''}`.trim() : `Instructor #${instructor.user_id}`,
        lessonType: selectedService.skill,
        date: bookingDate,
        startTime: selectedSlot.time,
        endTime: calculateEndTime(selectedSlot.time, duration),
        duration,
        location: '', // Let user enter their address on confirmation page
        basePrice,
        serviceFee,
        totalAmount,
        bookingType,
        paymentStatus: 'pending' as any,
        freeCancellationUntil:
          bookingType === BookingType.STANDARD
            ? new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
            : undefined,
      };

      // Store booking data for payment page
      sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
      sessionStorage.setItem('serviceId', String(selectedService.id));

      // Use navigation state manager to track booking flow properly
      navigationStateManager.saveBookingFlow({
        date: selectedSlot.date,
        time: selectedSlot.time,
        duration,
        instructorId
        // availableDuration will be recalculated on restore
      }, 'profile');

      if (!token) {
        // User not authenticated - store booking intent and redirect to login
        storeBookingIntent({
          instructorId: instructor.user_id,
          serviceId: selectedService.id,
          date: selectedSlot.date,
          time: selectedSlot.time,
          duration,
          skipModal: true,
        });

        // Redirect to login with payment page as return URL
        // Use replace to avoid polluting browser history
        const returnUrl = `/student/booking/confirm`;
        nextRouter.replace(`/login?redirect=${encodeURIComponent(returnUrl)}`);
      } else {
        // User is authenticated - go directly to payment page (NO MODAL)
        nextRouter.push('/student/booking/confirm');
      }
    }
  };

  // Initialize weekStart to today for rolling 7-day window
  useEffect(() => {
    // Always use today as the start for consistency
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    setWeekStart(today);
  }, [instructorId]);

  // Check for stored selected slot ONLY when returning from payment/auth pages
  useEffect(() => {
    // Use navigation state manager to handle slot restoration intelligently
    const restoredSlot = navigationStateManager.getBookingFlow(instructorId);

    if (restoredSlot) {
      // Initially restore without availableDuration - it will be recalculated
      // when availability data loads
      setSelectedSlot({
        date: restoredSlot.date,
        time: restoredSlot.time,
        duration: restoredSlot.duration,
        // Don't restore availableDuration - will be recalculated below
      });
      setIsSlotUserSelected(true); // Restored slots are considered user-selected
      setHasRestoredIntent(true);

      // Don't change weekStart here - keep it consistent with initial load (today)
      // This prevents the calendar from jumping to a different week
    }

    // Check for booking intent (from login flow)
    const bookingIntent = getBookingIntent();

    if (bookingIntent && bookingIntent.instructorId === instructorId) {
      // If skipModal flag is set, user already went through login and should go to payment
      if (bookingIntent.skipModal) {
        // The login redirect should have gone directly to /student/booking/confirm
        // But if we're here, clear the intent
        clearBookingIntent();
      } else {
        // Normal flow: restore slot and open modal
        setSelectedSlot({
          date: bookingIntent.date,
          time: bookingIntent.time,
          duration: bookingIntent.duration,
        });
        setIsSlotUserSelected(true); // Booking intent slots are considered user-selected
        setHasRestoredIntent(true);

        const token = localStorage.getItem('access_token');
        if (token) {
          bookingModal.openBookingModal({
            date: bookingIntent.date,
            time: bookingIntent.time,
            duration: bookingIntent.duration,
          });
        }

        clearBookingIntent();
      }
    }
  }, [instructorId]);

  // Recalculate availableDuration when availability data loads and we have a selected slot
  useEffect(() => {
    if (availability && selectedSlot && !selectedSlot.availableDuration) {
      // We have a selected slot but no availableDuration - recalculate it
      const dayData = availability.availability_by_date?.[selectedSlot.date];
      if (dayData?.available_slots) {
        // Parse the start hour from the time string
        const startHour = parseInt(selectedSlot.time.split(':')[0]);

        // Find the slot that contains this start time
        const containingSlot = dayData.available_slots.find((slot: any) => {
          const slotStart = parseInt(slot.start_time.split(':')[0]);
          const slotEnd = parseInt(slot.end_time.split(':')[0]);
          return startHour >= slotStart && startHour < slotEnd;
        });

        if (containingSlot) {
          // Calculate how many minutes are available from the start time to the end of the slot
          const slotEndHour = parseInt(containingSlot.end_time.split(':')[0]);
          const availableHours = slotEndHour - startHour;
          const calculatedDuration = availableHours * 60;

          // Update the selected slot with the calculated available duration
          setSelectedSlot(prev => prev ? {
            ...prev,
            availableDuration: calculatedDuration
          } : null);
        }
      }
    }
  }, [availability, selectedSlot]);

  useEffect(() => {
    // IMPORTANT: Race Condition Fix
    // This checks for pending slot restoration BEFORE auto-selecting.
    // Without this check, the auto-selection useEffect would run with stale state
    // and override the restored slot selection when navigating back from payment.
    // The restoredSlot check ensures we skip auto-selection if there's a saved slot
    // waiting to be restored from sessionStorage.
    const restoredSlot = navigationStateManager.getBookingFlow(instructorId);

    // Only auto-select a slot if:
    // 1. We have availability data
    // 2. No slot is currently selected
    // 3. We haven't restored a booking intent
    // 4. There's no slot waiting to be restored
    if (availability && availability.availability_by_date && !selectedSlot && !hasRestoredIntent && !restoredSlot) {
      // Pre-select the earliest available slot
      const dates = Object.keys(availability.availability_by_date).sort();
      for (const date of dates) {
        const dayData = availability.availability_by_date[date];
        if (!dayData.is_blackout && dayData.available_slots.length > 0) {
          const autoSelectedSlot = {
            date,
            time: dayData.available_slots[0].start_time,
            duration: 60 // Default duration
          };
          setSelectedSlot(autoSelectedSlot);
          setIsSlotUserSelected(false); // Auto-selected slots are not user-selected
          break;
        }
      }
    }
  }, [availability, selectedSlot, hasRestoredIntent, instructorId]);


  if (isLoading || (rateSecs !== null) || isFetching) {
    return (
      <>
        <RateLimitBanner />
        <InstructorProfileSkeleton />
      </>
    );
  }

  if ((error && rateSecs === null) || !instructor) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <div className="text-center py-12">
          <h2 className="text-2xl font-semibold mb-4">Unable to load instructor profile</h2>
          <p className="text-muted-foreground mb-6">
            There was an error loading this instructor's profile. Please try again.
          </p>
          <div className="flex gap-4 justify-center">
            <Button onClick={() => window.location.reload()} variant="outline">
              Try again
            </Button>
            <Button onClick={() => router.back()} variant="default">
              Back to search
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header - matching search results page */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4 sticky top-0 z-50">
        <div className="flex items-center justify-between max-w-full">
          <div className="flex items-center gap-4">
            <a href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </a>
            <Button
              variant="ghost"
              onClick={() => router.back()}
              className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Results
            </Button>
          </div>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6 max-w-7xl">
        {/* Mobile Layout - unchanged */}
        <div className="lg:hidden space-y-6">
          <InstructorHeader instructor={instructor} />

          <section>
            <h2 className="text-xl font-semibold mb-4">Services & Pricing</h2>
            <ServiceCards
              services={instructor.services}
              selectedSlot={selectedSlot}
              onBookService={(service, duration) => handleBookingClick(service, duration)}
            />
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-4">Availability This Week</h2>
            <AvailabilityCalendar instructorId={instructor.id} />
          </section>

          <ReviewsSection instructorId={instructor.id} />
        </div>

        {/* Desktop Layout - Fixed Layout */}
        <div className="hidden lg:block space-y-6">
          {/* Header with integrated Save Button */}
          <InstructorHeader instructor={instructor} />


          {/* Services Section */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex gap-8">
              {/* Services & Pricing - reduced width */}
              <div className="flex-[1.4] max-w-lg">
                <h2 className="text-lg text-gray-600 mb-4">Services & Pricing</h2>
                <ServiceCards
                  services={instructor.services}
                  selectedSlot={selectedSlot}
                  onBookService={(service, duration) => handleBookingClick(service, duration)}
                />
              </div>

              {/* Lesson Locations */}
              <div className="flex-[1]">
                <h2 className="text-lg text-gray-600 mb-4">Lesson Locations</h2>
                <div className="rounded-lg border border-purple-100 p-4" style={{ backgroundColor: 'rgb(249, 247, 255)' }}>
                  <div className="grid grid-cols-4 gap-4">
                    {/* Travel to you */}
                    {instructor.areas_of_service && instructor.areas_of_service.length > 0 && (
                      <div>
                        <div className="text-lg font-bold mb-2">Travel to you</div>
                        <div className="text-xs text-gray-600 space-y-0.5 ml-3">
                          <div>• Upper West Side</div>
                          <div>• Midtown</div>
                          <div>• Upper East Side</div>
                          <div>• Chelsea</div>
                          <div>• Park Slope</div>
                          <div>• Williamsburg</div>
                          <div>• DUMBO</div>
                          <div>• Long Island City</div>
                          <div>• Astoria</div>
                          <button className="text-purple-700 hover:text-purple-800 text-xs font-medium mt-1">
                            See more
                          </button>
                        </div>
                      </div>
                    )}

                    {/* My location - example: show if instructor has a studio */}
                    {true && ( // Replace with actual condition
                      <div>
                        <div className="text-lg font-bold mb-2">My location</div>
                        <div className="text-xs text-gray-600 ml-3">
                          <div>• Private studio in Manhattan</div>
                        </div>
                      </div>
                    )}

                    {/* Neutral location - example: show if instructor uses public spaces */}
                    {true && ( // Replace with actual condition
                      <div>
                        <div className="text-lg font-bold mb-2">Neutral location</div>
                        <div className="text-xs text-gray-600 ml-3">
                          <div>• Parks and outdoor spaces</div>
                          <div>• Community centers</div>
                        </div>
                      </div>
                    )}

                    {/* Online */}
                    {true && ( // Replace with actual condition
                      <div>
                        <div className="text-lg font-bold mb-2">Online</div>
                        <div className="text-xs text-gray-600 ml-3">
                          <div>• Video call lessons available</div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>



          {/* Reviews Section */}
          <div className="bg-white rounded-xl border border-gray-200 p-6" data-reviews-section>
            <ReviewsSection instructorId={instructor.id} />
          </div>
        </div>
      </div>

      {/* Sticky Booking Button - Mobile Only */}
      <BookingButton
        instructor={instructor}
        className="lg:hidden"
        onBook={() => handleBookingClick()}
      />

      {/* Time Selection Modal */}
      {instructor && bookingModal.isOpen && (
        <TimeSelectionModal
          isOpen={bookingModal.isOpen}
          onClose={bookingModal.closeBookingModal}
          instructor={{
            user_id: instructor.user_id,
            user: instructor.user ? {
              first_name: instructor.user.first_name,
              last_initial: instructor.user.last_initial
            } : {
              first_name: 'Instructor',
              last_initial: '#'
            },
            services: instructor.services.map(s => ({
              id: s.id,
              skill: s.skill || '',
              hourly_rate: s.hourly_rate,
              duration_options: s.duration_options || [60]
            }))
          }}
          preSelectedDate={bookingModal.selectedDate || ''}
          preSelectedTime={bookingModal.selectedTime || ''}
          onTimeSelected={(selection) => {
            // When user selects a time, mark it as user-selected and proceed to booking
            const newSlot = {
              date: selection.date,
              time: selection.time,
              duration: selection.duration
            };
            setSelectedSlot(newSlot);
            setIsSlotUserSelected(true);
            bookingModal.closeBookingModal();

            // Automatically proceed to booking confirmation page with the selected time
            const selectedService = instructor?.services[0]; // Use first service as default
            if (selectedService) {
              // Create booking data directly since we have all the info
              const token = localStorage.getItem('access_token');
              const bookingDate = new Date(newSlot.date + 'T' + newSlot.time);
              const hourlyRate = selectedService.hourly_rate;
              const totalPrice = hourlyRate * (newSlot.duration / 60);
              const basePrice = totalPrice;
              const serviceFee = calculateServiceFee(basePrice);
              const totalAmount = calculateTotalAmount(basePrice);
              const bookingType = determineBookingType(bookingDate);

              const paymentBookingData: BookingPayment = {
                bookingId: '',
                instructorId: String(instructor.user_id),
                instructorName: instructor.user ? `${instructor.user.first_name} ${instructor.user.last_initial ? instructor.user.last_initial + '.' : ''}`.trim() : `Instructor #${instructor.user_id}`,
                lessonType: selectedService.skill || 'Lesson',
                date: bookingDate,
                startTime: newSlot.time,
                endTime: calculateEndTime(newSlot.time, newSlot.duration),
                duration: newSlot.duration,
                location: '', // Let user enter their address on confirmation page
                basePrice,
                serviceFee,
                totalAmount,
                bookingType,
                paymentStatus: 'pending' as any,
                freeCancellationUntil:
                  bookingType === BookingType.STANDARD
                    ? new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
                    : undefined,
              };

              // Store booking data for payment page
              sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
              sessionStorage.setItem('serviceId', String(selectedService.id));

              // Use navigation state manager to track booking flow properly
              navigationStateManager.saveBookingFlow({
                date: newSlot.date,
                time: newSlot.time,
                duration: newSlot.duration,
                instructorId
              }, 'profile');

              if (!token) {
                // User not authenticated - store booking intent and redirect to login
                storeBookingIntent({
                  instructorId: instructor.user_id,
                  serviceId: selectedService.id,
                  date: newSlot.date,
                  time: newSlot.time,
                  duration: newSlot.duration,
                  skipModal: true,
                });

                // Redirect to login with payment page as return URL
                const returnUrl = `/student/booking/confirm`;
                nextRouter.replace(`/login?redirect=${encodeURIComponent(returnUrl)}`);
              } else {
                // User is authenticated - go directly to payment page
                nextRouter.push('/student/booking/confirm');
              }
            }
          }}
        />
      )}
    </div>
  );
}

export default function InstructorProfilePage() {
  return (
    <Suspense fallback={<InstructorProfileSkeleton />}>
      <InstructorProfileContent />
    </Suspense>
  );
}

// Configure dynamic route for Vercel
export const dynamic = 'force-dynamic';
export const dynamicParams = true;
