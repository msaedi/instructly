import { Skeleton } from '@/components/ui/skeleton';
import { Card } from '@/components/ui/card';

export function InstructorProfileSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      {/* Mobile Header Skeleton */}
      <div className="sticky top-0 z-40 bg-background border-b lg:hidden">
        <div className="flex items-center justify-between p-4">
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-8 w-8" />
        </div>
      </div>

      {/* Desktop Header Skeleton */}
      <div className="hidden lg:block border-b">
        <div className="container mx-auto px-4 py-4 max-w-6xl">
          <div className="flex items-center justify-between">
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-10 w-40" />
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6 max-w-6xl">
        <div className="grid gap-8 lg:grid-cols-3">
          {/* Left Column */}
          <div className="lg:col-span-2 space-y-8">
            {/* Header Skeleton */}
            <div className="flex flex-col lg:flex-row gap-6">
              <Skeleton className="h-24 w-24 lg:h-32 lg:w-32 rounded-full" />
              <div className="flex-1 space-y-3">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-40" />
                <div className="flex gap-2">
                  <Skeleton className="h-6 w-24" />
                  <Skeleton className="h-6 w-20" />
                </div>
              </div>
            </div>

            {/* About Section Skeleton */}
            <div>
              <Skeleton className="h-6 w-20 mb-4" />
              <Skeleton className="h-4 w-full mb-2" />
              <Skeleton className="h-4 w-5/6 mb-2" />
              <Skeleton className="h-4 w-4/6" />
            </div>

            {/* Services Section Skeleton */}
            <div>
              <Skeleton className="h-6 w-32 mb-4" />
              <div className="grid gap-4 md:grid-cols-2">
                <Card className="p-6">
                  <Skeleton className="h-6 w-32 mb-2" />
                  <Skeleton className="h-4 w-full mb-4" />
                  <Skeleton className="h-10 w-full" />
                </Card>
                <Card className="p-6">
                  <Skeleton className="h-6 w-32 mb-2" />
                  <Skeleton className="h-4 w-full mb-4" />
                  <Skeleton className="h-10 w-full" />
                </Card>
              </div>
            </div>

            {/* Availability Section - Mobile */}
            <div className="lg:hidden">
              <Skeleton className="h-6 w-40 mb-4" />
              <Card className="p-4">
                <div className="space-y-3">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex justify-between items-center">
                      <Skeleton className="h-4 w-20" />
                      <div className="flex gap-2">
                        <Skeleton className="h-8 w-16" />
                        <Skeleton className="h-8 w-16" />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>

            {/* Reviews Section Skeleton */}
            <div>
              <Skeleton className="h-6 w-24 mb-4" />
              <div className="space-y-4">
                <Card className="p-6">
                  <Skeleton className="h-4 w-24 mb-2" />
                  <Skeleton className="h-3 w-full mb-1" />
                  <Skeleton className="h-3 w-3/4" />
                </Card>
                <Card className="p-6">
                  <Skeleton className="h-4 w-24 mb-2" />
                  <Skeleton className="h-3 w-full mb-1" />
                  <Skeleton className="h-3 w-3/4" />
                </Card>
              </div>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            {/* Availability Section - Desktop */}
            <div className="hidden lg:block">
              <Skeleton className="h-6 w-28 mb-4" />
              <Card className="p-4">
                <div className="space-y-3">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex justify-between items-center">
                      <Skeleton className="h-4 w-20" />
                      <div className="flex gap-2">
                        <Skeleton className="h-8 w-16" />
                        <Skeleton className="h-8 w-16" />
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>

            {/* Info Cards Skeleton */}
            <Card className="p-6">
              <Skeleton className="h-5 w-24 mb-3" />
              <Skeleton className="h-4 w-full mb-2" />
              <Skeleton className="h-4 w-3/4" />
            </Card>
            <Card className="p-6">
              <Skeleton className="h-5 w-32 mb-3" />
              <Skeleton className="h-4 w-full mb-2" />
              <Skeleton className="h-4 w-5/6 mb-2" />
              <Skeleton className="h-4 w-4/6" />
            </Card>
          </div>
        </div>
      </div>

      {/* Sticky Booking Button Skeleton - Mobile */}
      <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-background border-t lg:hidden">
        <Skeleton className="h-12 w-full rounded-lg" />
      </div>
    </div>
  );
}
