// frontend/components/InstructorCard.tsx
'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Star, MapPin, Check, Heart } from 'lucide-react';
import { Instructor, ServiceCatalogItem } from '@/types/api';
import { useEffect, useState } from 'react';
import { publicApi } from '@/features/shared/api/client';
import { navigationStateManager } from '@/lib/navigation/navigationStateManager';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { favoritesApi } from '@/services/api/favorites';
import { toast } from 'sonner';

interface InstructorCardProps {
  instructor: Instructor;
  nextAvailableSlots?: Array<{
    date: string;
    time: string;
    displayText: string;
  }>;
  onViewProfile?: () => void;
  onBookNow?: () => void;
  onTimeSlotClick?: () => void;
}

export default function InstructorCard({
  instructor,
  nextAvailableSlots = [],
  onViewProfile,
  onBookNow,
  onTimeSlotClick,
}: InstructorCardProps) {
  const router = useRouter();
  const { user } = useAuth();
  const [serviceCatalog, setServiceCatalog] = useState<ServiceCatalogItem[]>([]);
  const [isFavorited, setIsFavorited] = useState(false);
  const [isLoadingFavorite, setIsLoadingFavorite] = useState(false);

  // Fetch service catalog on mount
  useEffect(() => {
    const fetchServiceCatalog = async () => {
      try {
        const response = await publicApi.getCatalogServices();
        if (response.data) {
          setServiceCatalog(response.data);
        }
      } catch (error) {
        console.error('Failed to fetch service catalog:', error);
      }
    };
    fetchServiceCatalog();
  }, []);

  // Check favorite status on mount if user is logged in
  useEffect(() => {
    if (user && instructor?.user_id) {
      favoritesApi.check(instructor.user_id)
        .then(res => setIsFavorited(res.is_favorited))
        .catch(() => setIsFavorited(false));
    }
  }, [user, instructor?.user_id]);

  // Filter out past availability slots
  const futureAvailableSlots = nextAvailableSlots.filter((slot) => {
    const slotDateTime = new Date(`${slot.date}T${slot.time}`);
    return slotDateTime > new Date();
  });

  const getMinimumRate = () => {
    if (instructor.services.length === 0) return 0;
    return Math.min(...instructor.services.map((s) => s.hourly_rate));
  };

  // Helper function to get service name from catalog
  const getServiceName = (serviceId: string): string => {
    const service = serviceCatalog.find((s) => s.id === serviceId);
    return service?.name || `Service ${serviceId}`;
  };

  const getInstructorServiceNames = (): string => {
    if (instructor.services.length === 0) return 'Expert Instructor';
    const serviceNames = instructor.services.map((s) => getServiceName(s.service_catalog_id));
    return serviceNames.join(', ') + ' Expert';
  };

  const handleInstantBook = (date: string, time: string) => {
    // Navigate to quick booking page with pre-selected time
    router.push(`/book/${instructor.user_id}?date=${date}&time=${time}`);
  };

  const handleFavoriteClick = async () => {
    // Guest users - redirect to login
    if (!user) {
      const returnUrl = `/search?instructorToFavorite=${instructor.user_id}`;
      router.push(`/login?returnTo=${encodeURIComponent(returnUrl)}`);
      return;
    }

    if (isLoadingFavorite) return;

    // Optimistic update
    setIsFavorited(!isFavorited);
    setIsLoadingFavorite(true);

    try {
      if (isFavorited) {
        await favoritesApi.remove(instructor.user_id);
        toast.success('Removed from favorites');
      } else {
        await favoritesApi.add(instructor.user_id);
        toast.success('Added to favorites!');
      }
    } catch (error) {
      // Revert on error
      setIsFavorited(isFavorited);
      toast.error('Failed to update favorite');
      console.error('Favorite toggle error:', error);
    } finally {
      setIsLoadingFavorite(false);
    }
  };

  return (
    <div
      className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden hover:shadow-lg transition-shadow"
      data-testid="instructor-card"
    >
      <div className="p-6">
        {/* Header with photo placeholder and name */}
        <div className="flex items-start mb-4">
          <div className="w-20 h-20 bg-gray-200 rounded-lg mr-4 flex-shrink-0">
            <div className="w-full h-full flex items-center justify-center text-gray-400">
              Photo
            </div>
          </div>
          <div className="flex-1">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h3 className="font-semibold text-lg text-gray-900" data-testid="instructor-name">
                  {instructor.user.first_name} {instructor.user.last_initial ? `${instructor.user.last_initial}.` : ''}
                </h3>
                <p className="text-gray-600">{getInstructorServiceNames()}</p>
                <div className="flex items-center mt-1">
                  <Star className="h-4 w-4 text-yellow-500 fill-current" />
                  <span className="ml-1 text-sm font-medium">{instructor.rating || 4.8}</span>
                  <span className="text-sm text-gray-600 ml-1">
                    ({instructor.total_reviews || 0} reviews)
                  </span>
                </div>
              </div>
              <button
                onClick={handleFavoriteClick}
                disabled={isLoadingFavorite}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
                aria-label={user ? "Toggle favorite" : "Sign in to save"}
                title={!user ? "Sign in to save this instructor" : isFavorited ? "Remove from favorites" : "Add to favorites"}
              >
                <Heart
                  className="h-5 w-5"
                  fill={isFavorited ? '#ff0000' : 'none'}
                  color={isFavorited ? '#ff0000' : '#666'}
                />
              </button>
            </div>
          </div>
        </div>

        {/* Info row */}
        <div className="flex items-center text-sm text-gray-600 mb-4">
          <MapPin className="h-4 w-4 mr-1" />
          <span>{instructor.areas_of_service[0] || 'Manhattan'}</span>
          <span className="mx-2">·</span>
          <span className="font-medium text-gray-900" data-testid="instructor-price">
            ${instructor.services[0]?.hourly_rate || 0}/hour
          </span>
        </div>

        {/* Features */}
        <div className="space-y-2 mb-4">
          <div className="flex items-center text-sm text-gray-600">
            <Check className="h-4 w-4 text-green-600 mr-2" />
            Background checked
          </div>
          <div className="flex items-center text-sm text-gray-600">
            <Check className="h-4 w-4 text-green-600 mr-2" />
            Teaches all levels
          </div>
          <div className="flex items-center text-sm text-gray-600">
            <Check className="h-4 w-4 text-green-600 mr-2" />
            {instructor.years_experience} years experience
          </div>
        </div>

        {/* Next available times */}
        <div className="mb-4">
          <p className="text-sm font-medium text-gray-900 mb-2">Next available:</p>
          {futureAvailableSlots.length > 0 ? (
            <div className="flex gap-2 flex-wrap">
              {futureAvailableSlots.slice(0, 3).map((slot, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    onTimeSlotClick?.();
                    handleInstantBook(slot.date, slot.time);
                  }}
                  className="px-3 py-2 bg-gray-100 rounded-lg text-sm hover:bg-gray-200"
                >
                  <div className="font-medium">{slot.displayText.split(' ')[0]}</div>
                  <div className="text-gray-600">
                    {slot.displayText.split(' ').slice(1).join(' ')}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="text-sm text-gray-500 italic">No upcoming availability</div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <Link
            href={`/instructors/${instructor.user_id}`}
            className="flex-1 text-center py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 dark:text-white transition-colors"
            onClick={() => {
              // Clear navigation state when viewing profile from search - this is a fresh navigation
              navigationStateManager.clearBookingFlow();
              onViewProfile?.();
            }}
          >
            View Profile
          </Link>
          <Link
            href={`/book/${instructor.user_id}`}
            className="flex-1 text-center py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700 transition-colors"
            onClick={onBookNow}
          >
            Book Now →
          </Link>
        </div>
      </div>
    </div>
  );
}
