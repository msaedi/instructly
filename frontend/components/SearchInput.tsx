// frontend/components/SearchInput.tsx
'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Search } from 'lucide-react';
import { logger } from '@/lib/logger';

interface SearchInputProps {
  initialValue: string;
}

export default function SearchInput({ initialValue }: SearchInputProps) {
  const [searchQuery, setSearchQuery] = useState(initialValue);
  const router = useRouter();
  const searchParams = useSearchParams();

  const handleSubmit = () => {
    const params = new URLSearchParams(searchParams);
    if (searchQuery.trim()) {
      params.set('search', searchQuery.trim());
    } else {
      params.delete('search');
    }
    router.push(`/instructors?${params.toString()}`);
    logger.debug('Search query submitted', { query: searchQuery });
  };

  return (
    <div className="max-w-2xl mx-auto mb-8">
      <div className="relative">
        <input
          type="text"
          placeholder="Search by name, skill, or area..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleSubmit();
            }
          }}
          className="w-full px-4 py-2 pl-10 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-700 dark:text-white"
          aria-label="Search instructors"
        />
        <Search className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" aria-hidden="true" />
      </div>
    </div>
  );
}
