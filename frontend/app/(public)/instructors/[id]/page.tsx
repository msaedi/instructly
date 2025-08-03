'use client';
// frontend/app/(public)/instructors/[id]/page.tsx

import { Suspense, useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft, Heart } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
import { format } from 'date-fns';

function InstructorProfileContent() {
  const params = useParams();
  const router = useRouter();
  const instructorId = params.id as string;
  const [selectedSlot, setSelectedSlot] = useState<{ date: string; time: string; duration: number; availableDuration?: number } | null>(null);
  const [weekStart, setWeekStart] = useState<Date | null>(null);

  const { data: instructor, isLoading, error } = useInstructorProfile(instructorId);
  const { data: availability } = useInstructorAvailability(
    instructorId,
    weekStart ? format(weekStart, 'yyyy-MM-dd') : undefined
  );
  const { isSaved, toggleSave, isLoading: isSaveLoading } = useSaveInstructor(
    instructor?.id ? Number(instructor.id) : 0
  );
  const bookingModal = useBookingModal();

  // Initialize weekStart to today for rolling 7-day window
  useEffect(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    setWeekStart(today);
  }, []);

  useEffect(() => {
    if (availability && !selectedSlot) {
      // Pre-select the earliest available slot
      const dates = Object.keys(availability.availability_by_date).sort();
      for (const date of dates) {
        const dayData = availability.availability_by_date[date];
        if (!dayData.is_blackout && dayData.available_slots.length > 0) {
          setSelectedSlot({
            date,
            time: dayData.available_slots[0].start_time,
            duration: 60 // Default duration
          });
          break;
        }
      }
    }
  }, [availability, selectedSlot]);


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
              onBookService={(service, duration) => bookingModal.openBookingModal({ service, duration })}
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
                  onSelectSlot={(date: string, time: string, duration?: number, availableDuration?: number) =>
                    setSelectedSlot({ date, time, duration: duration || 60, availableDuration })
                  }
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
              onBookService={(service, duration) => bookingModal.openBookingModal({ service, duration })}
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
        onBook={() => bookingModal.openBookingModal()}
      />

      {/* Booking Modal */}
      {instructor && bookingModal.isOpen && (
        <BookingModal
          isOpen={bookingModal.isOpen}
          onClose={bookingModal.closeBookingModal}
          onContinueToBooking={(bookingData) => {
            // Handle booking continuation
            bookingModal.closeBookingModal();
          }}
          instructor={{
            id: instructor.id,
            user_id: instructor.user_id,
            user: {
              full_name: instructor.user?.full_name || `Instructor #${instructor.user_id}`,
              email: instructor.user?.email || ''
            },
            bio: instructor.bio,
            areas_of_service: instructor.areas_of_service,
            years_experience: instructor.years_experience,
            services: instructor.services.map(s => ({
              id: s.id,
              skill: s.skill,
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
