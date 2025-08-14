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
import BookingModal from '@/features/student/booking/components/BookingModal';
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
  const [weekStart, setWeekStart] = useState<Date | null>(null);
  const [hasRestoredIntent, setHasRestoredIntent] = useState(false);

  const { data: instructor, isLoading, error } = useInstructorProfile(instructorId);
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
        location: instructor.areas_of_service[0] || 'NYC',
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
          break;
        }
      }
    }
  }, [availability, selectedSlot, hasRestoredIntent, instructorId]);


  if (isLoading) {
    return <InstructorProfileSkeleton />;
  }

  if (error || !instructor) {
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
      {/* Mobile Header with Back and Save */}
      <div className="sticky top-0 z-40 bg-background border-b lg:hidden">
        <div className="flex items-center justify-between p-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.back()}
            className="flex items-center gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleSave}
            disabled={isSaveLoading}
          >
            <Heart className={`h-5 w-5 ${isSaved ? 'fill-current text-red-500' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Desktop Header */}
      <div className="hidden lg:block border-b">
        <div className="container mx-auto px-4 py-4 max-w-6xl">
          <div className="flex items-center">
            <Button
              variant="ghost"
              onClick={() => router.back()}
              className="flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Results
            </Button>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6 max-w-7xl">
        {/* Mobile Layout - unchanged */}
        <div className="lg:hidden space-y-8">
          <InstructorHeader instructor={instructor} />

          <section>
            <h2 className="text-xl font-semibold mb-4">About</h2>
            <p className="text-muted-foreground leading-relaxed">
              {instructor.bio || 'No bio available'}
            </p>
          </section>

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

          {/* Three-Card Single Container */}
          <div className="border rounded-lg bg-white overflow-hidden">
            <div className="grid grid-cols-[1fr_2fr_1fr] min-h-[400px]">
              {/* Column 1: About */}
              <div className="p-6 flex flex-col h-full" style={{ minHeight: '350px' }}>
                <h3 className="text-lg font-semibold mb-4 pb-2 border-b -mx-6 px-6">About</h3>
                <div className="flex flex-col flex-1">
                  {/* Top section - Experience */}
                  <div className="flex-shrink-0">
                    {instructor.years_experience > 0 && (
                      <div className="mb-4">
                        <p className="font-medium text-sm">Experience:</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          {instructor.years_experience} years teaching
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Middle section - Languages (vertically centered, left-aligned) */}
                  <div className="flex-1 flex items-center">
                    <div>
                      <p className="font-medium text-sm">Languages:</p>
                      <p className="text-sm text-muted-foreground mt-1">English, Spanish</p>
                    </div>
                  </div>

                  {/* Bottom section - Bio (anchored to bottom) */}
                  <div className="flex-shrink-0 mt-auto">
                    {instructor.bio && (
                      <div>
                        <p className="font-medium text-sm">Bio:</p>
                        <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
                          {instructor.bio}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Column 2: Availability */}
              <div className="p-6">
                <AvailabilityGrid
                  instructorId={instructor.id}
                  weekStart={weekStart}
                  onWeekChange={setWeekStart}
                  selectedSlot={selectedSlot}
                  onSelectSlot={(date: string, time: string, duration?: number, availableDuration?: number) => {
                    setSelectedSlot({ date, time, duration: duration || 60, availableDuration });
                  }}
                />
              </div>

              {/* Column 3: Location */}
              <div className="p-6 flex flex-col h-full">
                <h3 className="text-lg font-semibold mb-4 pb-2 border-b -mx-6 px-6">Location</h3>
                <div className="flex flex-col flex-1 justify-between">
                  <div className="space-y-3">
                    {instructor.areas_of_service && instructor.areas_of_service.length > 0 ? (
                      <>
                        <div>
                          <div className="font-medium text-sm mb-1">Manhattan</div>
                          <div className="text-sm text-muted-foreground space-y-1 ml-4">
                            <div>• Upper West Side</div>
                            <div>• Midtown</div>
                          </div>
                        </div>
                        <div>
                          <div className="font-medium text-sm mb-1">Brooklyn</div>
                          <div className="text-sm text-muted-foreground ml-4">
                            <div>• Park Slope</div>
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="text-sm text-muted-foreground">No location specified</div>
                    )}
                  </div>
                  <Button variant="outline" className="w-full" size="sm">
                    📍 View on Map
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Services Section - Below Three Cards */}
          <div className="border rounded-lg bg-white p-6">
            <h2 className="text-lg font-semibold mb-4 pb-2 border-b">Services & Pricing</h2>
            <ServiceCards
              services={instructor.services}
              selectedSlot={selectedSlot}
              onBookService={(service, duration) => handleBookingClick(service, duration)}
            />
          </div>

          {/* Reviews Section */}
          <div className="border rounded-lg bg-white p-6">
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

      {/* Booking Modal */}
      {instructor && bookingModal.isOpen && (
        <BookingModal
          isOpen={bookingModal.isOpen}
          onClose={bookingModal.closeBookingModal}
          onContinueToBooking={() => {
            // The BookingModal handles the booking flow internally
            // This callback is not actually used but required by the interface
          }}
          instructor={{
            id: instructor.id,
            user_id: instructor.user_id,
            user: instructor.user ? {
              first_name: instructor.user.first_name,
              last_initial: instructor.user.last_initial
              // No email for privacy
            } : {
              first_name: 'Instructor',
              last_initial: '#',
              // No email for privacy
            },
            bio: instructor.bio,
            areas_of_service: instructor.areas_of_service,
            years_experience: instructor.years_experience,
            services: instructor.services.map(s => ({
              id: s.id,
              skill: s.skill || '',
              hourly_rate: s.hourly_rate,
              duration: s.duration_options?.[0] || 60,
              duration_options: s.duration_options || [60],
              description: s.description || '',
              is_active: s.is_active
            }))
          }}
          selectedDate={bookingModal.selectedDate || ''}
          selectedTime={bookingModal.selectedTime || ''}
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
