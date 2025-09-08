'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useLessonDetails } from '@/hooks/useMyLessons';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { isApiError } from '@/lib/react-query/api';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { ArrowLeft, Star, Heart, DollarSign } from 'lucide-react';
import { toast } from 'sonner';
import { getStripe } from '@/features/student/payment/utils/stripe';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import { logger } from '@/lib/logger';

export default function ReviewPage() {
  const params = useParams();
  const router = useRouter();
  const lessonId = params['id'] as string;
  const { isAuthenticated, isLoading: isAuthLoading, redirectToLogin } = useAuth();
  const queryClient = useQueryClient();

  const [rating, setRating] = useState(0);
  const [hoveredRating, setHoveredRating] = useState(0);
  const [review, setReview] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [addToFavorites, setAddToFavorites] = useState(false);
  const [hasExistingReview, setHasExistingReview] = useState(false);
  const [selectedTip, setSelectedTip] = useState<number | null>(null);
  const [customTip, setCustomTip] = useState('');
  const [showCustomTip, setShowCustomTip] = useState(false);

  const { data: lesson, isLoading, error } = useLessonDetails(lessonId);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthLoading && !isAuthenticated) {
      redirectToLogin(`/student/review/${lessonId}`);
    }
  }, [isAuthLoading, isAuthenticated, redirectToLogin, lessonId]);

  // Handle 401 errors by redirecting to login
  useEffect(() => {
    if (error && isApiError(error) && error.status === 401) {
      redirectToLogin(`/student/review/${lessonId}`);
    }
  }, [error, redirectToLogin, lessonId]);

  // Check if review already exists
  useEffect(() => {
    if (!lesson?.id) return;
    const checkExistingReview = async () => {
      try {
        const { reviewsApi } = await import('@/services/api/reviews');
        const r = await reviewsApi.getByBooking(lesson.id);
        setHasExistingReview(!!r);
      } catch (error) {
        logger.error('Failed to check existing review', error as Error);
      }
    };
    void checkExistingReview();
  }, [lesson]);

  // Show loading while checking auth
  if (isAuthLoading || isLoading) {
    return <ReviewPageLoading />;
  }

  // Don't render content if not authenticated
  if (!isAuthenticated) {
    return null;
  }

  if (error || !lesson) {
    return (
      <div className="min-h-screen">
        {/* Header - matching other pages */}
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
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
              onClick={() => router.push('/student/lessons?tab=history')}
              className="bg-[#6A0DAD] hover:bg-[#6A0DAD] text-white"
            >
              Back to My Lessons
            </Button>
          </Card>
        </div>
      </div>
    );
  }

  // Get instructor name (first name only, no initials on this page)
  const instructorName = lesson.instructor?.first_name || 'your instructor';
  const instructorFirstName = lesson.instructor?.first_name || 'your instructor';

  const handleSubmit = async () => {
    if (rating === 0) {
      toast.error('Please select a rating');
      return;
    }

    setIsSubmitting(true);
    try {
      const { reviewsApi } = await import('@/services/api/reviews');
      const tipAmount = showCustomTip ? parseFloat(customTip) : selectedTip;
      const payload: {
        booking_id: string;
        rating: number;
        review_text?: string;
        tip_amount_cents?: number;
      } = {
        booking_id: lessonId,
        rating,
      };

      if (review) {
        payload.review_text = review;
      }

      if (tipAmount) {
        payload.tip_amount_cents = Math.round((tipAmount as number) * 100);
      }

      const res = await reviewsApi.submit(payload);

      // If a tip PI is created, confirm it on the client
      if (res.tip_client_secret) {
        const stripe = await getStripe();
        if (stripe) {
          const { error: stripeError } = await stripe.confirmCardPayment(res.tip_client_secret);
          if (stripeError) {
            toast.error(stripeError.message || 'Tip payment failed');
          } else {
            toast.success('Tip processed successfully');
          }
        }
      }

      // If user wants to add to favorites and rating > 3
      if (rating > 3 && addToFavorites) {
        try {
          const { favoritesApi } = await import('@/services/api/favorites');
          await favoritesApi.add(lesson.instructor_id);
          toast.success('Added to favorites!');
        } catch (error) {
          logger.error('Failed to add to favorites', error as Error);
        }
      }

      toast.success('Review submitted successfully!');

      // Invalidate lessons caches so History reflects Reviewed status immediately
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      await queryClient.invalidateQueries({ queryKey: ['bookings'] });

      // Redirect back to lessons (history tab)
      router.push('/student/lessons?tab=history');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to submit review. Please try again.';
      toast.error(message);
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link className="inline-block" href="/">
            <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Back Button */}
        <div className="mb-6">
          <Button
            variant="ghost"
            onClick={() => router.push(`/student/lessons/${lessonId}`)}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Lesson Details
          </Button>
        </div>

        {/* Main Content */}
        <Card className="p-6 sm:p-8 bg-white rounded-xl border border-gray-200 max-w-3xl mx-auto">
          {hasExistingReview ? (
            // Show existing review message
            <div className="text-center py-12">
              <div className="mb-6">
                <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h1 className="text-2xl font-bold text-gray-900 mb-3">
                  You already submitted a review for {instructorName}
                </h1>
                <p className="text-gray-600">
                  This feedback will show up on {instructorFirstName}&apos;s public reviews.
                </p>
              </div>
              <Button
                onClick={() => router.push('/student/lessons?tab=history')}
                className="bg-[#6A0DAD] hover:bg-[#6A0DAD] text-white px-8 py-2.5"
              >
                Back to My Lessons
              </Button>
            </div>
          ) : (
            <>
              {/* Header */}
              <div className="text-center mb-8">
                <h1 className="text-2xl font-bold text-gray-900 mb-3">We value your feedback</h1>
                <p className="text-gray-600">
                  Your review helps {instructorFirstName} and future clients. It will appear on {instructorFirstName}&apos;s public profile.
                </p>
              </div>

          {/* Rating Section */}
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-gray-900 text-center mb-4">
              How was your experience with {instructorFirstName}?
            </h2>
            <div className="flex justify-center gap-2">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  onClick={() => setRating(star)}
                  onMouseEnter={() => setHoveredRating(star)}
                  onMouseLeave={() => setHoveredRating(0)}
                  className="transition-transform hover:scale-110 focus:outline-none focus:scale-110"
                  aria-label={`Rate ${star} stars`}
                >
                  <Star
                    className={`h-10 w-10 ${
                      star <= (hoveredRating || rating)
                        ? 'fill-yellow-400 text-yellow-400'
                        : 'text-gray-300'
                    } transition-colors`}
                  />
                </button>
              ))}
            </div>
            {rating > 0 && (
              <p className="text-center mt-2 text-sm text-gray-600">
                {rating === 1 && 'Poor'}
                {rating === 2 && 'Fair'}
                {rating === 3 && 'Good'}
                {rating === 4 && 'Very Good'}
                {rating === 5 && 'Excellent'}
              </p>
            )}
          </div>

          {/* Review Box */}
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Please share your feedback</h3>
            <p className="text-sm text-gray-600 mb-4">
              What went well? Anything to improve? Your honest feedback helps others.
            </p>
            <textarea
              value={review}
              onChange={(e) => setReview(e.target.value)}
              placeholder={`Tell others about your experience with ${instructorFirstName}...`}
              className="w-full min-h-[150px] p-4 border border-gray-300 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-[#6A0DAD] focus:border-transparent"
              maxLength={500}
            />
            <p className="text-xs text-gray-500 mt-1 text-right">
              {review.length}/500 characters
            </p>
          </div>

          {/* Tipping Section */}
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Want to thank {instructorFirstName} for a job well done?
            </h3>
            <p className="text-sm text-gray-600 mb-4">
              Tips go directly to {instructorFirstName} and are optional.
            </p>

            <div className="space-y-3">
              {/* Quick-select tip buttons */}
              <div className="flex flex-wrap gap-2">
                {[5, 10, 20].map((amount) => (
                  <button
                    key={amount}
                    onClick={() => {
                      setSelectedTip(amount);
                      setShowCustomTip(false);
                      setCustomTip('');
                    }}
                    className={`px-6 py-2.5 rounded-lg font-medium transition-colors ${
                      selectedTip === amount && !showCustomTip
                        ? 'bg-[#6A0DAD] text-white'
                        : 'bg-white text-gray-700 border-2 border-gray-300 hover:border-purple-400'
                    }`}
                  >
                    ${amount}
                  </button>
                ))}
                <button
                  onClick={() => {
                    setShowCustomTip(true);
                    setSelectedTip(null);
                  }}
                  className={`px-6 py-2.5 rounded-lg font-medium transition-colors ${
                    showCustomTip
                      ? 'bg-[#6A0DAD] text-white'
                      : 'bg-white text-gray-700 border-2 border-gray-300 hover:border-purple-400'
                  }`}
                >
                  Other
                </button>
              </div>

              {/* Custom tip input */}
              {showCustomTip && (
                <div className="flex items-center gap-2">
                  <div className="relative flex-1 max-w-xs">
                    <DollarSign className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
                    <input
                      type="number"
                      value={customTip}
                      onChange={(e) => {
                        const value = e.target.value;
                        if (value === '' || (parseFloat(value) >= 0 && parseFloat(value) <= 999)) {
                          setCustomTip(value);
                        }
                      }}
                      placeholder="Enter amount"
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#6A0DAD] focus:border-transparent"
                      min="0"
                      max="999"
                      step="1"
                    />
                  </div>
                </div>
              )}

              {/* Transparency note */}
              <p className="text-xs text-gray-500 italic">
                100% of your tip goes to {instructorFirstName}.
              </p>
            </div>
          </div>

          {/* Add to Favorites Section - Only show when rating is 4 or 5 stars */}
          {rating > 3 && (
            <div className="mb-8 p-4 bg-purple-50 rounded-lg border border-purple-200">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={addToFavorites}
                  onChange={(e) => setAddToFavorites(e.target.checked)}
                  className="mt-1 h-5 w-5 text-purple-600 border-gray-300 rounded focus:ring-[#6A0DAD]"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Heart className="h-5 w-5 text-purple-600" />
                    <h3 className="font-semibold text-gray-900">
                      Add {instructorFirstName} to My Favorite Instructors
                    </h3>
                  </div>
                  <p className="text-sm text-gray-600">
                    Add past instructors to your favorites to build your go-to team, so you can easily hire them again in the future.
                  </p>
                </div>
              </label>
            </div>
          )}

              {/* Submit Button */}
              <div className="flex justify-center">
                <Button
                  onClick={handleSubmit}
                  disabled={rating === 0 || isSubmitting}
                  className={`px-8 py-2.5 text-base font-medium rounded-lg ${
                    rating === 0 || isSubmitting
                      ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      : 'bg-[#6A0DAD] hover:bg-[#6A0DAD] text-white'
                  }`}
                >
                  {isSubmitting ? 'Submitting...' : 'Submit'}
                </Button>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function ReviewPageLoading() {
  return (
    <div className="min-h-screen">
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#6A0DAD] hover:text-[#6A0DAD] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <div className="animate-pulse">
              <div className="w-10 h-10 bg-gray-200 rounded-full"></div>
            </div>
          </div>
        </div>
      </header>
      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        <Card className="p-8">
          <div className="space-y-4">
            <div className="h-6 w-48 bg-gray-200 rounded"></div>
            <div className="h-10 w-32 bg-gray-200 rounded"></div>
            <div className="h-24 w-full bg-gray-200 rounded"></div>
            <div className="h-8 w-48 bg-gray-200 rounded"></div>
          </div>
        </Card>
      </div>
    </div>
  );
}
