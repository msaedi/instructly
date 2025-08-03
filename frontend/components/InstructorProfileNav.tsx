// frontend/components/InstructorProfileNav.tsx
'use client';

import { useRouter } from 'next/navigation';
import { ChevronLeft } from 'lucide-react';

interface InstructorProfileNavProps {
  instructorName: string;
}

export default function InstructorProfileNav({ instructorName }: InstructorProfileNavProps) {
  const router = useRouter();

  const handleBackClick = () => {
    // Always use browser history for back navigation
    // This provides the most natural user experience
    router.back();
  };

  return (
    <nav className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center">
            <button
              onClick={handleBackClick}
              className="mr-4 p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <ChevronLeft className="h-6 w-6 text-gray-600 dark:text-gray-300" />
            </button>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              {instructorName}
            </h1>
          </div>
          <button
            onClick={handleBackClick}
            className="text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
          >
            Back
          </button>
        </div>
      </div>
    </nav>
  );
}
