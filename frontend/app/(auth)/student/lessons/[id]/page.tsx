'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useLessonDetails } from '@/hooks/useMyLessons';
import { format } from 'date-fns';
import { ArrowLeft, Calendar, Clock, DollarSign, MapPin, MessageCircle } from 'lucide-react';
import { logger } from '@/lib/logger';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { InstructorInfo } from '@/components/lessons/InstructorInfo';
import { RescheduleModal } from '@/components/lessons/modals/RescheduleModal';
import { CancelWarningModal } from '@/components/lessons/modals/CancelWarningModal';
import { ChatModal } from '@/components/chat/ChatModal';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { isApiError } from '@/lib/react-query/api';
import { StatusBadge } from '@/components/ui/status-badge';
import UserProfileDropdown from '@/components/UserProfileDropdown';

type LessonPaymentSummary = {
  lesson_amount: number;
  service_fee: number;
  credit_applied: number;
  subtotal: number;
  tip_amount: number;
  tip_paid: number;
  total_paid: number;
  tip_status?: string | null;
};

export default function LessonDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const lessonId = params['id'] as string;
  const { isAuthenticated, isLoading: isAuthLoading, redirectToLogin, user } = useAuth();

  // Preserve the tab parameter from sessionStorage
  const [fromTab] = useState(() => {
    // Check if we have a stored tab in sessionStorage
    if (typeof window !== 'undefined') {
      const storedTab = sessionStorage.getItem('lessonsTab');
      if (storedTab === 'history' || storedTab === 'upcoming') {
        return storedTab;
      }
    }
    return 'upcoming';
  });

  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showChatModal, setShowChatModal] = useState(false);
  const [reviewed, setReviewed] = useState(false);

  const { data: lesson, isLoading, error } = useLessonDetails(lessonId);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthLoading && !isAuthenticated) {
      redirectToLogin(`/student/lessons/${lessonId}`);
    }
  }, [isAuthLoading, isAuthenticated, redirectToLogin, lessonId]);

  // Handle 401 errors by redirecting to login
  useEffect(() => {
    if (error && isApiError(error) && error.status === 401) {
      redirectToLogin(`/student/lessons/${lessonId}`);
    }
  }, [error, redirectToLogin, lessonId]);

  // Check if a review exists for this booking to toggle CTA
  useEffect(() => {
    if (!lesson?.id) return;
    let mounted = true;
    (async () => {
      try {
        const { reviewsApi } = await import('@/services/api/reviews');
        const r = await reviewsApi.getByBooking(lesson.id);
        if (mounted) setReviewed(!!r);
      } catch {
        if (mounted) setReviewed(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [lesson?.id]);

  // Show loading while checking auth
  if (isAuthLoading) {
    return <LessonDetailsLoading />;
  }

  // Don't render content if not authenticated
  if (!isAuthenticated) {
    return null;
  }

  if (isLoading) {
    return <LessonDetailsLoading />;
  }

  if (error || !lesson) {
    return (
      <div className="min-h-screen">
        {/* Header - matching other pages */}
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
          <Card className="p-8 text-center bg-white rounded-xl border border-gray-200">
            <p className="text-lg text-gray-600 mb-4">Unable to load lesson details</p>
            <Button
              onClick={() => router.push(`/student/lessons?tab=${fromTab}`)}
              className="bg-[#7E22CE] hover:bg-[#7E22CE] text-white"
            >
              Back to My Lessons
            </Button>
          </Card>
        </div>
      </div>
    );
  }

  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const now = new Date();
  const isPastLesson = lessonDateTime < now;
  const isUpcoming = lesson.status === 'CONFIRMED' && !isPastLesson;
  const isCompleted = lesson.status === 'COMPLETED' || (lesson.status === 'CONFIRMED' && isPastLesson);
  const isCancelled = lesson.status === 'CANCELLED';

  // Check if lesson is within 12 hours (cannot reschedule)
  const hoursUntilLesson = (lessonDateTime.getTime() - now.getTime()) / (1000 * 60 * 60);
  const canReschedule = isUpcoming && hoursUntilLesson >= 12;

  // Check if cancelled within 12 hours (full charge)
  let wasCancelledLate = false;
  if (lesson.status === 'CANCELLED' && lesson.cancelled_at) {
    const cancelledDate = new Date(lesson.cancelled_at);
    const hoursBeforeLessonWhenCancelled = (lessonDateTime.getTime() - cancelledDate.getTime()) / (1000 * 60 * 60);
    wasCancelledLate = hoursBeforeLessonWhenCancelled < 12;
  }

  const formattedDate = format(lessonDateTime, 'EEE MMM d');
  const formattedTime = format(lessonDateTime, 'h:mm a');
  // Reschedule annotation (if this was created from another booking)
  const rescheduledFrom = (lesson as unknown as Record<string, unknown>)['rescheduled_from_booking_id'] as string | undefined;
  let rescheduledFromText: string | null = null;
  if (rescheduledFrom && (lesson as unknown as Record<string, unknown>)['rescheduled_from']) {
    try {
      const prev = (lesson as unknown as Record<string, unknown>)['rescheduled_from'] as Record<string, unknown>;
      const prevDt = new Date(`${prev['booking_date']}T${prev['start_time']}`);
      rescheduledFromText = `Rescheduled from ${format(prevDt, 'MMM d')}, ${format(prevDt, 'h:mm a')}`;
    } catch {
      rescheduledFromText = null;
    }
  }

  const paymentSummary = (lesson as typeof lesson & { payment_summary?: LessonPaymentSummary }).payment_summary;
  const formatCurrency = (value: number | undefined) => {
    if (typeof value !== 'number' || Number.isNaN(value)) {
      return '0.00';
    }
    return value.toFixed(2);
  };
  const safeNumber = (value: unknown): number | undefined =>
    typeof value === 'number' && Number.isFinite(value) ? value : undefined;
  const fallbackLessonAmount = safeNumber((lesson as { total_price?: number }).total_price) ?? 0;
  const fallbackServiceFee = safeNumber((lesson as { service_fee?: number }).service_fee);
  const fallbackCreditApplied = safeNumber((lesson as { credit_applied?: number }).credit_applied);
  const fallbackTipAmount = safeNumber((lesson as { tip_amount?: number }).tip_amount);
  const fallbackTipPaid = safeNumber((lesson as { tip_paid?: number }).tip_paid);
  const fallbackTotalPaid = safeNumber((lesson as { final_amount?: number }).final_amount);
  const resolvedLessonAmount = paymentSummary?.lesson_amount ?? fallbackLessonAmount;
  const resolvedServiceFee = paymentSummary?.service_fee ?? fallbackServiceFee ?? 0;
  const resolvedCreditApplied = paymentSummary?.credit_applied ?? fallbackCreditApplied ?? 0;
  const resolvedTipAmount = paymentSummary?.tip_amount ?? fallbackTipAmount ?? 0;
  const resolvedTipPaid = paymentSummary?.tip_paid ?? fallbackTipPaid ?? 0;
  const tipDisplayAmount = resolvedTipPaid > 0 ? resolvedTipPaid : resolvedTipAmount;
  const hasCreditApplied = resolvedCreditApplied > 0;
  const hasTip = tipDisplayAmount > 0;
  const tipPending = hasTip && resolvedTipPaid < resolvedTipAmount;
  const totalPaid =
    paymentSummary?.total_paid ??
    fallbackTotalPaid ??
    resolvedLessonAmount + resolvedServiceFee - resolvedCreditApplied + Math.max(tipDisplayAmount, 0);

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link className="inline-block" href="/">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Back Button */}
        <div className="mb-6 bg-white rounded-lg border border-gray-200 px-3 py-0.5">
          <button
            onClick={() => router.push(`/student/lessons?tab=${fromTab}`)}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-700 py-1 px-2 rounded transition-colors cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to My Lessons
          </button>
        </div>

        {/* Main Content */}
        <Card className="p-6 sm:p-8 bg-white rounded-xl border border-gray-200">
          {/* Lesson Title and Status */}
          <div className="mb-6">
            <div className="flex items-start justify-between">
              <h1 className="text-2xl sm:text-3xl font-bold text-[#7E22CE]">
                {lesson.service_name}
              </h1>
              {isCompleted && (
                <StatusBadge variant="success" label="Completed" showIcon={true} />
              )}
            </div>
            {rescheduledFromText && (
              <p className="mt-2 text-sm text-gray-500">{rescheduledFromText}</p>
            )}
          </div>

        {/* Date, Time, Price */}
        <div className="space-y-3 mb-6">
          <div className="flex items-center gap-3">
            <Calendar className="h-5 w-5 text-gray-500" />
            <span className="text-lg text-gray-700">{formattedDate}</span>
          </div>
          <div className="flex items-center gap-3">
            <Clock className="h-5 w-5 text-gray-500" />
            <span className="text-lg text-gray-700">{formattedTime}</span>
          </div>
          <div className="flex items-center gap-3">
            <DollarSign className="h-5 w-5 text-gray-500" />
            <span className="text-lg text-gray-700">{lesson.total_price.toFixed(2)}</span>
          </div>
        </div>

        {/* Instructor Info */}
        <div className="mb-6">
          <InstructorInfo
            instructor={{
              id: lesson.instructor?.id || lesson.instructor_id,
              ...((lesson.instructor as unknown as { first_name?: string })?.first_name && {
                first_name: (lesson.instructor as unknown as { first_name?: string }).first_name
              }),
              ...((lesson.instructor as unknown as { last_name?: string })?.last_name && {
                last_name: (lesson.instructor as unknown as { last_name?: string }).last_name
              }),
              ...((lesson.instructor as unknown as { last_initial?: string })?.last_initial && {
                last_initial: (lesson.instructor as unknown as { last_initial?: string }).last_initial
              }),
              ...((lesson.instructor as unknown as { email?: string })?.email && {
                email: (lesson.instructor as unknown as { email?: string }).email
              }),
              ...((lesson.instructor as unknown as { has_profile_picture?: boolean })?.has_profile_picture !== undefined && {
                has_profile_picture: (lesson.instructor as unknown as { has_profile_picture?: boolean }).has_profile_picture
              }),
              ...((lesson.instructor as unknown as { profile_picture_version?: number })?.profile_picture_version && {
                profile_picture_version: (lesson.instructor as unknown as { profile_picture_version?: number }).profile_picture_version
              }),
            }}
          />
        </div>

        {/* Action Buttons */}
        <div className="mb-8">
          {isUpcoming && null}
          {isCompleted && (
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() => router.push(`/instructors/${lesson.instructor_id}`)}
                className="bg-[#7E22CE] hover:bg-[#7E22CE] text-white border-transparent rounded-lg py-2.5 px-6 text-sm font-medium"
              >
                Book Again
              </Button>
              {reviewed ? (
                <span className="bg-gray-100 text-gray-600 border-2 border-gray-300 rounded-lg py-2.5 px-6 text-sm font-medium cursor-default">
                  Reviewed
                </span>
              ) : (
                <Button
                  onClick={() => router.push(`/student/review/${lesson.id}`)}
                  className="bg-white text-[#7E22CE] border-2 border-[#7E22CE] hover:bg-purple-50 rounded-lg py-2.5 px-6 text-sm font-medium"
                >
                  Review & tip
                </Button>
              )}
              <Button
                onClick={() => setShowChatModal(true)}
                className="bg-white text-gray-400 border-2 border-gray-300 hover:bg-gray-50 rounded-lg py-2.5 px-6 text-sm font-medium"
              >
                <MessageCircle className="h-4 w-4 mr-1" />
                Chat history
              </Button>
            </div>
          )}
          {isCancelled && (
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() => router.push(`/instructors/${lesson.instructor_id}`)}
                className="bg-[#7E22CE] hover:bg-[#7E22CE] text-white border-transparent rounded-lg py-2.5 px-6 text-sm font-medium"
              >
                Book Again
              </Button>
              <Button
                onClick={() => setShowChatModal(true)}
                className="bg-white text-gray-400 border-2 border-gray-300 hover:bg-gray-50 rounded-lg py-2.5 px-6 text-sm font-medium"
              >
                <MessageCircle className="h-4 w-4 mr-1" />
                Chat history
              </Button>
            </div>
          )}
        </div>

        <Separator />

        {/* Lesson Details Section */}
        <div className="mt-8 space-y-6">
          <div>
            <h2 className="text-xl font-semibold mb-4 text-gray-700">Lesson Details</h2>

            {/* Location */}
            <div className="mb-4">
              <h3 className="font-medium mb-2 text-gray-600">Location</h3>
              {lesson.meeting_location ? (
                <>
                  <p className="text-gray-500">{lesson.meeting_location}</p>
                  {isUpcoming && lesson.meeting_location.toLowerCase() !== 'online' && (
                    <Button
                      variant="link"
                      className="px-0 h-auto text-[#7E22CE] hover:text-[#7E22CE]"
                      onClick={() => logger.info('View map clicked')}
                    >
                      <MapPin className="h-4 w-4 mr-1" />
                      View map
                    </Button>
                  )}
                </>
              ) : (
                <p className="text-gray-500">{lesson.service_area || 'NYC'}</p>
              )}
            </div>

            {/* Notes */}
            {(lesson.student_note || lesson.instructor_note) && (
              <div>
                <h3 className="font-medium mb-2 text-gray-600">Description</h3>
                <p className="text-gray-500">
                  {lesson.student_note || lesson.instructor_note}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Manage Booking Section for Upcoming */}
        {isUpcoming && (
          <>
            <Separator className="my-8" />
            <div>
              <h2 className="text-xl font-semibold mb-4 text-gray-700">Manage Booking</h2>
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-3">
                  <Button
                    onClick={() => setShowRescheduleModal(true)}
                    disabled={!canReschedule}
                    className={`flex-1 sm:flex-initial rounded-lg py-2.5 px-6 text-sm font-medium ${
                      canReschedule
                        ? 'bg-[#7E22CE] hover:bg-[#7E22CE] text-white border-transparent'
                        : 'bg-gray-200 text-gray-400 cursor-not-allowed border-transparent'
                    }`}
                  >
                    Reschedule lesson
                  </Button>
                  <Button
                    onClick={() => setShowCancelModal(true)}
                    variant="outline"
                    className="flex-1 sm:flex-initial bg-white text-[#7E22CE] border-2 border-[#7E22CE] hover:bg-purple-50 rounded-lg py-2.5 px-6 text-sm font-medium"
                  >
                    Cancel lesson
                  </Button>
                </div>
                {!canReschedule && hoursUntilLesson < 12 && (
                  <p className="text-sm text-gray-500">
                    Cannot reschedule within 12 hours of lesson start time
                  </p>
                )}
              </div>
            </div>
          </>
        )}

        {/* Receipt Section for Completed or Late Cancellation */}
        {(isCompleted || wasCancelledLate) && (
          <>
            <Separator className="my-8" />
            <div>
              <h2 className="text-xl font-semibold mb-4 text-gray-700">Receipt</h2>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-500">Date of Lesson</span>
                  <span className="text-gray-700">{format(lessonDateTime, 'EEE MMM d')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">
                    ${lesson.hourly_rate.toFixed(2)}/hr x {lesson.duration_minutes / 60} hr
                  </span>
                  <span className="text-gray-700">${formatCurrency(resolvedLessonAmount)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Platform fee</span>
                  <span className="text-gray-700">${formatCurrency(resolvedServiceFee)}</span>
                </div>
                {hasCreditApplied && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Credit applied</span>
                    <span className="text-gray-700">-${formatCurrency(resolvedCreditApplied)}</span>
                  </div>
                )}
                {hasTip && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">
                      Tip{tipPending ? ' (pending)' : ''}
                    </span>
                    <span className="text-gray-700">
                      ${formatCurrency(tipDisplayAmount)}
                    </span>
                  </div>
                )}
                <Separator />
                <div className="flex justify-between font-semibold text-gray-900">
                  <span>Total</span>
                  <span>${formatCurrency(totalPaid)}</span>
                </div>
                <div className="flex justify-between text-gray-500">
                  <span>Paid</span>
                  <span>${formatCurrency(totalPaid)}</span>
                </div>
                {tipPending && (
                  <p className="text-xs text-gray-500 pt-2">
                    Tip will be finalized once your payment method is confirmed.
                  </p>
                )}
                {wasCancelledLate && (
                  <p className="text-xs text-gray-500 pt-2">
                    This lesson was cancelled less than 12 hours before the scheduled time and was charged in full.
                  </p>
                )}
                {isCompleted && (
                  <p className="text-xs text-gray-500 pt-2">
                    For cancellations between 12–24 hours before a lesson, you&apos;ll be charged and receive a platform credit for the amount.
                  </p>
                )}
              </div>
            </div>
          </>
        )}
        </Card>

        {/* Modals */}
        {lesson && (
          <>
            <RescheduleModal
              isOpen={showRescheduleModal}
              onClose={() => setShowRescheduleModal(false)}
              lesson={({
                ...lesson,
                updated_at: (lesson as unknown as { updated_at?: string }).updated_at ?? new Date().toISOString(),
              } as unknown) as import('@/features/shared/api/types').Booking}
            />
            <CancelWarningModal
              isOpen={showCancelModal}
              onClose={() => setShowCancelModal(false)}
              lesson={({
                ...lesson,
                updated_at: (lesson as unknown as { updated_at?: string }).updated_at ?? new Date().toISOString(),
              } as unknown) as import('@/features/shared/api/types').Booking}
              onReschedule={() => {
                setShowCancelModal(false);
                setShowRescheduleModal(true);
              }}
            />
            {user && lesson.instructor && (
              <ChatModal
                isOpen={showChatModal}
                onClose={() => setShowChatModal(false)}
                bookingId={lesson.id}
                currentUserId={user.id}
                currentUserName={user.first_name}
                otherUserName={lesson.instructor.first_name || 'Instructor'}
                lessonTitle={lesson.service_name}
                lessonDate={format(new Date(`${lesson.booking_date}T${lesson.start_time}`), 'MMM d, yyyy')}
                isReadOnly={isCompleted || isCancelled}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function LessonDetailsLoading() {
  return (
    <div className="min-h-screen">
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link className="inline-block" href="/">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <div className="animate-pulse">
              <div className="w-10 h-10 bg-gray-200 rounded-full"></div>
            </div>
          </div>
        </div>
      </header>
      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <div className="flex items-center mb-6">
          <Skeleton className="h-10 w-32" />
        </div>
        <Card className="p-6 sm:p-8 bg-white rounded-xl border border-gray-200">
          <Skeleton className="h-8 w-48 mb-6" />
          <div className="space-y-3 mb-6">
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-6 w-32" />
          </div>
          <Skeleton className="h-20 w-full mb-8" />
          <Skeleton className="h-10 w-32" />
        </Card>
      </div>
    </div>
  );
}
