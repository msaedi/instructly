'use client';
// frontend/app/(public)/instructors/[id]/page.tsx

import { Suspense, useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { InstructorHeader } from '@/features/instructor-profile/components/InstructorHeader';
import { ServiceCards } from '@/features/instructor-profile/components/ServiceCards';
import { ReviewsSection } from '@/features/instructor-profile/components/ReviewsSection';
import { BookingButton } from '@/features/instructor-profile/components/BookingButton';
import { InstructorProfileSkeleton } from '@/features/instructor-profile/components/InstructorProfileSkeleton';
import { useInstructorProfile } from '@/features/instructor-profile/hooks/useInstructorProfile';
import { useBookingModal } from '@/features/instructor-profile/hooks/useBookingModal';
import { useInstructorAvailability } from '@/hooks/queries/useInstructorAvailability';
import { useInstructorCoverage } from '@/src/api/services/instructors';
import TimeSelectionModal from '@/features/student/booking/components/TimeSelectionModal';
import { useRouter as useNextRouter } from 'next/navigation';
import { calculateEndTime } from '@/features/shared/utils/booking';
import { BookingPayment, PAYMENT_STATUS } from '@/features/student/payment';
import { BookingType } from '@/features/shared/types/booking';
import { determineBookingType } from '@/features/shared/utils/paymentCalculations';
import { navigationStateManager } from '@/lib/navigation/navigationStateManager';
import { format } from 'date-fns';
import { useBackgroundConfig } from '@/lib/config/backgroundProvider';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { getString, getNumber, isFeatureCollection } from '@/lib/typesafe';
import type { InstructorService } from '@/types/instructor';
import { at } from '@/lib/ts/safe';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { WhereTheyTeach } from '@/components/instructor/WhereTheyTeach';

import { storeBookingIntent, getBookingIntent, clearBookingIntent } from '@/features/shared/utils/booking';

function RateLimitBanner({ initialSeconds, onRetry }: { initialSeconds: number; onRetry: () => void }) {
  const [rateSecs, setRateSecs] = useState(initialSeconds);

  useEffect(() => {
    const interval = setInterval(() => {
      setRateSecs((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          void onRetry();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [onRetry]);

  if (rateSecs <= 0) {
    return null;
  }

  return (
    <div className="container mx-auto px-4 max-w-6xl">
      <div className="mb-4 rounded-md bg-yellow-50 border border-yellow-200 text-yellow-900 px-3 py-2 text-sm">
        Our hamsters are sprinting. Give them {rateSecs}s.
      </div>
    </div>
  );
}

function InstructorProfileContent() {
  const params = useParams();
  const router = useRouter();
  const nextRouter = useNextRouter();
  const instructorId = params['id'] as string;
  type SelectedSlot = {
    date: string;
    time: string;
    duration: number;
    availableDuration?: number;
  };

  const initialRestore = useMemo(() => {
    const restoredSlot = navigationStateManager.getBookingFlow(instructorId);
    const bookingIntent = getBookingIntent();
    let slot: SelectedSlot | null = null;
    let openModalFromIntent = false;

    if (restoredSlot) {
      slot = {
        date: restoredSlot.date,
        time: restoredSlot.time,
        duration: restoredSlot.duration,
      };
    } else if (bookingIntent && bookingIntent.instructorId === instructorId) {
      slot = {
        date: bookingIntent.date,
        time: bookingIntent.time,
        duration: bookingIntent.duration,
      };
      openModalFromIntent = !bookingIntent.skipModal;
    }

    return { restoredSlot, bookingIntent, slot, openModalFromIntent };
  }, [instructorId]);
  const [selectedSlot, setSelectedSlot] = useState<SelectedSlot | null>(
    () => initialRestore.slot
  );
  const [isSlotUserSelected, setIsSlotUserSelected] = useState(
    () => Boolean(initialRestore.slot)
  ); // Track if slot was manually selected by user
  const weekStart = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  }, []);
  const { isAuthenticated } = useAuth();

  const { data: instructor, isLoading, error, refetch, isFetching } = useInstructorProfile(instructorId);
  const { setActivity } = useBackgroundConfig();
  const rateLimitSeconds = useMemo(() => {
    if (!error) return null;
    const message = getString(error, 'message', '');
    const isRateLimited = /hamsters|Too Many Requests|rate limit/i.test(message);
    if (!isRateLimited) return null;
    const m = message.match(/(\d+)s/);
    const secondStr = m ? at(m, 1) : undefined;
    return secondStr ? parseInt(secondStr, 10) : 3;
  }, [error]);


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
  const availabilityInstructorId = instructor?.user_id || '';
  const { data: availability } = useInstructorAvailability(
    availabilityInstructorId,
    weekStart ? format(weekStart, 'yyyy-MM-dd') : undefined
  );

  const bookingModal = useBookingModal();
  useEffect(() => {
    if (initialRestore.restoredSlot) {
      navigationStateManager.clearBookingFlow();
    }
  }, [initialRestore.restoredSlot]);

  useEffect(() => {
    if (initialRestore.bookingIntent) {
      clearBookingIntent();
    }
  }, [initialRestore.bookingIntent]);

  useEffect(() => {
    if (!initialRestore.bookingIntent || !initialRestore.openModalFromIntent) {
      return;
    }
    if (typeof window === 'undefined') {
      return;
    }
    bookingModal.openBookingModal({
      date: initialRestore.bookingIntent.date,
      time: initialRestore.bookingIntent.time,
      duration: initialRestore.bookingIntent.duration,
    });
  }, [bookingModal, initialRestore.bookingIntent, initialRestore.openModalFromIntent]);
  const services = Array.isArray(instructor?.services) ? instructor.services : [];
  const offersTravel = services.some((service) => service.offers_travel === true);
  const offersAtLocation = services.some((service) => service.offers_at_location === true);
  const offersOnline = services.some((service) => service.offers_online === true);
  const shouldShowMap = offersTravel || offersAtLocation;
  const coverageInstructorId = instructor?.user_id || instructorId;
  const { data: coverage } = useInstructorCoverage(coverageInstructorId, {
    enabled: shouldShowMap && Boolean(coverageInstructorId),
  });

  const formatCityState = (address: string): string => {
    const parts = address.split(',').map((part) => part.trim()).filter(Boolean);
    if (parts.length >= 2) {
      const city = parts[parts.length - 2] || '';
      const stateRaw = parts[parts.length - 1] || '';
      const state = stateRaw.replace(/\b\d{5}(?:-\d{4})?\b/g, '').replace(/\s{2,}/g, ' ').trim();
      return [city, state].filter(Boolean).join(', ');
    }
    return '';
  };
  const studioPins: Array<{ lat: number; lng: number; label?: string }> = [];
  if (instructor && offersAtLocation && Array.isArray(instructor.preferred_teaching_locations)) {
    for (const location of instructor.preferred_teaching_locations) {
      if (!location || typeof location !== 'object') continue;
      const approxLat = typeof location.approx_lat === 'number' ? location.approx_lat : undefined;
      const approxLng = typeof location.approx_lng === 'number' ? location.approx_lng : undefined;
      if (typeof approxLat !== 'number' || typeof approxLng !== 'number') continue;
      const neighborhood = typeof location.neighborhood === 'string' ? location.neighborhood.trim() : '';
      const labelFallback = typeof location.label === 'string' ? location.label.trim() : '';
      const addressFallback = typeof location.address === 'string'
        ? formatCityState(location.address)
        : '';
      const label = neighborhood || addressFallback || labelFallback || undefined;
      if (label) {
        studioPins.push({ lat: approxLat, lng: approxLng, label });
      } else {
        studioPins.push({ lat: approxLat, lng: approxLng });
      }
    }
  }
  const coverageCollection = isFeatureCollection(coverage) ? coverage : null;



  // Helper function to handle booking - opens availability modal; auth handled after time selection
  const handleBookingClick = (service?: InstructorService, serviceDuration?: number) => {
    const selectedService: InstructorService | undefined = service || instructor?.services[0]; // Use provided service or default to first
    const duration = serviceDuration || 60; // Use provided duration or default

    // Always open the booking modal to select a time; authentication is handled after selection
    if (!activeSelectedSlot || !hasUserSelectedSlot) {
      const modalOptions: {
        date?: string;
        time?: string;
        duration?: number;
        service?: unknown;
      } = {
        date: '',
        time: '',
        duration,
      };

      if (selectedService) {
        modalOptions.service = selectedService;
      }

      bookingModal.openBookingModal(modalOptions);
      return;
    }

    if (activeSelectedSlot && selectedService && instructor) {
      const bookingDate = new Date(activeSelectedSlot.date + 'T' + activeSelectedSlot.time);
      const hourlyRate = getNumber(selectedService, 'hourly_rate', 0);
      const totalPrice = hourlyRate * (duration / 60);
      const basePrice = totalPrice;
      const totalAmount = basePrice;
      const bookingType = determineBookingType(bookingDate);

      const paymentBookingData: BookingPayment = {
        bookingId: '',
        instructorId: String(instructor.user_id),
        instructorName: instructor.user ? `${instructor.user.first_name} ${instructor.user.last_initial ? instructor.user.last_initial + '.' : ''}`.trim() : `Instructor #${instructor.user_id}`,
        lessonType: getString(selectedService, 'skill', ''),
        date: bookingDate,
        startTime: activeSelectedSlot.time,
        endTime: calculateEndTime(activeSelectedSlot.time, duration),
        duration,
        location: '', // Let user enter their address on confirmation page
        basePrice,
        totalAmount,
        bookingType,
        paymentStatus: PAYMENT_STATUS.SCHEDULED,
        ...(bookingType === BookingType.STANDARD && {
          freeCancellationUntil: new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
        }),
      };

      // Store booking data for payment page
      sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
      sessionStorage.setItem('serviceId', String(selectedService.id));
      try {
        sessionStorage.setItem('selectedSlot', JSON.stringify({
          date: activeSelectedSlot.date,
          time: activeSelectedSlot.time,
          duration,
          instructorId: instructor.user_id,
        }));
      } catch {}

      // Use navigation state manager to track booking flow properly
      navigationStateManager.saveBookingFlow({
        date: activeSelectedSlot.date,
        time: activeSelectedSlot.time,
        duration,
        instructorId
        // availableDuration will be recalculated on restore
      }, 'profile');

      if (!isAuthenticated) {
        // User not authenticated - store booking intent and redirect to login
        const bookingIntent: {
          instructorId: string;
          serviceId?: string;
          date: string;
          time: string;
          duration: number;
          skipModal?: boolean;
        } = {
          instructorId: instructor.user_id,
          date: activeSelectedSlot.date,
          time: activeSelectedSlot.time,
          duration,
          skipModal: true,
        };

        const serviceId = getString(selectedService, 'id');
        if (serviceId) {
          bookingIntent.serviceId = serviceId;
        }

        storeBookingIntent(bookingIntent);
        const returnUrl = `/student/booking/confirm`;
        nextRouter.replace(`/login?redirect=${encodeURIComponent(returnUrl)}`);
      } else {
        // Authenticated - go directly to payment page
        nextRouter.push('/student/booking/confirm');
      }
    }
  };

  const autoSelectedSlot: SelectedSlot | null = (() => {
    if (!availability?.availability_by_date || selectedSlot) {
      return null;
    }
    const dates = Object.keys(availability.availability_by_date).sort();
    for (const date of dates) {
      const dayData = availability.availability_by_date[date];
      if (dayData && !dayData.is_blackout && dayData.available_slots.length > 0 && dayData.available_slots[0]) {
        return {
          date,
          time: dayData.available_slots[0].start_time,
          duration: 60,
        };
      }
    }
    return null;
  })();

  const activeSelectedSlot = (() => {
    const baseSlot = selectedSlot ?? autoSelectedSlot;
    if (!baseSlot) return null;
    if (baseSlot.availableDuration || !availability?.availability_by_date) return baseSlot;
    const dayData = availability.availability_by_date?.[baseSlot.date];
    if (!dayData?.available_slots) return baseSlot;

    const timeParts = baseSlot.time.split(':');
    const startHourStr = at(timeParts, 0);
    if (!startHourStr) return baseSlot;
    const startHour = parseInt(startHourStr);

    const containingSlot = dayData.available_slots.find((slot: Record<string, unknown>) => {
      const startTimeStr = getString(slot, 'start_time');
      const endTimeStr = getString(slot, 'end_time');
      if (!startTimeStr || !endTimeStr) return false;
      const startParts = startTimeStr.split(':');
      const endParts = endTimeStr.split(':');
      const slotStartStr = at(startParts, 0);
      const slotEndStr = at(endParts, 0);
      if (!slotStartStr || !slotEndStr) return false;
      const slotStart = parseInt(slotStartStr);
      const slotEnd = parseInt(slotEndStr);
      return startHour >= slotStart && startHour < slotEnd;
    });

    if (!containingSlot) {
      return baseSlot;
    }

    const slotEndTime = containingSlot.end_time.split(':');
    const slotEndHour = parseInt(slotEndTime[0] || '0');
    const availableHours = slotEndHour - startHour;
    const calculatedDuration = availableHours * 60;

    return {
      ...baseSlot,
      availableDuration: calculatedDuration,
    };
  })();

  const hasUserSelectedSlot = Boolean(selectedSlot && isSlotUserSelected);


  if (isLoading || rateLimitSeconds !== null || isFetching) {
    return (
      <>
        {rateLimitSeconds !== null ? (
          <RateLimitBanner
            key={`rate-limit-${getString(error, 'message', '')}`}
            initialSeconds={rateLimitSeconds}
            onRetry={refetch}
          />
        ) : null}
        <InstructorProfileSkeleton />
      </>
    );
  }

  if ((error && rateLimitSeconds === null) || !instructor) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <div className="text-center py-12">
          <h2 className="text-2xl font-semibold mb-4">Unable to load instructor profile</h2>
          <p className="text-muted-foreground mb-6">
            There was an error loading this instructor&apos;s profile. Please try again.
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
            <Link className="inline-block" href="/">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <Button
              variant="ghost"
              onClick={() => router.push('/instructor/dashboard')}
              className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Dashboard
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
          <div className="flex items-start">
            <InstructorHeader instructor={instructor} />
          </div>

          <section>
            <h2 className="text-xl font-semibold mb-4">Skills and pricing</h2>
            <ServiceCards
              services={instructor.services}
              selectedSlot={activeSelectedSlot}
              onBookService={(service, duration) => handleBookingClick(service, duration)}
            />
          </section>

          <WhereTheyTeach
            offersTravel={offersTravel}
            offersAtLocation={offersAtLocation}
            offersOnline={offersOnline}
            coverage={coverageCollection}
            studioPins={studioPins}
          />

          <ReviewsSection instructorId={instructor.user_id} />
        </div>

        {/* Desktop Layout - Fixed Layout */}
        <div className="hidden lg:block space-y-6">
          {/* Header with integrated Save Button */}
          <div className="flex items-start">
            <InstructorHeader instructor={instructor} />
          </div>


          {/* Skills & Lesson Options */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
              <h2 className="text-lg text-gray-900 dark:text-white mb-4">Skills and pricing</h2>
              <ServiceCards
                services={instructor.services}
                selectedSlot={activeSelectedSlot}
                onBookService={(service, duration) => handleBookingClick(service, duration)}
              />
            </div>
            <WhereTheyTeach
              offersTravel={offersTravel}
              offersAtLocation={offersAtLocation}
              offersOnline={offersOnline}
              coverage={coverageCollection}
              studioPins={studioPins}
            />
          </div>

          {/* Availability Grid removed per request */}
          {/* Reviews Section */}
          <div className="bg-white rounded-xl border border-gray-200 p-6" data-reviews-section>
            <ReviewsSection instructorId={instructor.user_id} />
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
              duration_options: s.duration_options || [60],
              location_types: s.location_types || []
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
              const bookingDate = new Date(newSlot.date + 'T' + newSlot.time);
              const hourlyRate = selectedService.hourly_rate;
              const totalPrice = hourlyRate * (newSlot.duration / 60);
              const basePrice = totalPrice;
              const totalAmount = basePrice;
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
                totalAmount,
                bookingType,
                paymentStatus: PAYMENT_STATUS.SCHEDULED,
                ...(bookingType === BookingType.STANDARD && {
                  freeCancellationUntil: new Date(bookingDate.getTime() - 24 * 60 * 60 * 1000)
                }),
              };

              // Store booking data for payment page
              sessionStorage.setItem('bookingData', JSON.stringify(paymentBookingData));
              sessionStorage.setItem('serviceId', String(selectedService.id));
              try {
                sessionStorage.setItem(
                  'selectedSlot',
                  JSON.stringify({ date: newSlot.date, time: newSlot.time, duration: newSlot.duration, instructorId })
                );
              } catch {}

              // Use navigation state manager to track booking flow properly
              navigationStateManager.saveBookingFlow({
                date: newSlot.date,
                time: newSlot.time,
                duration: newSlot.duration,
                instructorId
              }, 'profile');

              if (!isAuthenticated) {
                // User not authenticated - store booking intent and redirect to login
                const bookingIntent2: {
                  instructorId: string;
                  serviceId?: string;
                  date: string;
                  time: string;
                  duration: number;
                  skipModal?: boolean;
                } = {
                  instructorId: instructor.user_id,
                  date: newSlot.date,
                  time: newSlot.time,
                  duration: newSlot.duration,
                  skipModal: true,
                };

                const serviceId2 = getString(selectedService, 'id');
                if (serviceId2) {
                  bookingIntent2.serviceId = serviceId2;
                }

                storeBookingIntent(bookingIntent2);
                const returnUrl = `/student/booking/confirm`;
                nextRouter.replace(`/login?redirect=${encodeURIComponent(returnUrl)}`);
              } else {
                // Authenticated - go directly to payment page
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
