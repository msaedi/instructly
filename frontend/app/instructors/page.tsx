"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import Link from "next/link";
import { fetchAPI, API_ENDPOINTS } from '@/lib/api';

interface Instructor {
    id: number;
    user_id: number;
    bio: string;
    areas_of_service: string[];
    years_experience: number;
    created_at: string;
    updated_at: string | null;
    user: {
      full_name: string;
      email: string;
    };
    services: { 
      id: number;
      skill: string;
      hourly_rate: number;
      description: string | null;
    }[];
  }

export default function InstructorsPage() {
  const [instructors, setInstructors] = useState<Instructor[]>([]);
  const [filteredInstructors, setFilteredInstructors] = useState<Instructor[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    const fetchInstructors = async () => {
      try {
        const response = await fetchAPI(API_ENDPOINTS.INSTRUCTORS);
        if (!response.ok) {
          throw new Error("Failed to fetch instructors");
        }
        const data = await response.json();
        setInstructors(data);
        setFilteredInstructors(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred");
      } finally {
        setIsLoading(false);
      }
    };

    fetchInstructors();
  }, []);

  useEffect(() => {
    const filtered = instructors.filter((instructor) => {
        const searchLower = searchQuery.toLowerCase();
        return (
          instructor.user.full_name.toLowerCase().includes(searchLower) ||
          instructor.services.some((service) => service.skill.toLowerCase().includes(searchLower))
        );
      });
    setFilteredInstructors(filtered);
  }, [searchQuery, instructors]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-red-500 text-center">
          <h2 className="text-2xl font-bold mb-2">Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <>
    {/* Simple Navbar */}
    <nav className="bg-white shadow-sm border-b">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <Link href="/" className="text-2xl font-bold text-indigo-600">
            Instructly
          </Link>
          <Link href="/" className="text-gray-600 hover:text-gray-900">
            Back to Home
          </Link>
        </div>
      </div>
    </nav>
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-center mb-8">Find Your Perfect Instructor</h1>
      
      {/* Search Bar */}
      <div className="max-w-2xl mx-auto mb-8">
        <div className="relative">
          <input
            type="text"
            placeholder="Search by name or skill..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-4 py-2 pl-10 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <Search className="absolute left-3 top-2.5 h-5 w-5 text-gray-400" />
        </div>
      </div>

      {/* Instructor Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredInstructors.map((instructor) => (
          <div
            key={instructor.id}
            className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">{instructor.user.full_name}</h2>
            <p className="text-gray-600 mb-4 line-clamp-3">
              {instructor.bio.length > 100
                ? `${instructor.bio.substring(0, 100)}...`
                : instructor.bio}
            </p>
            
            {/* Services with individual pricing */}
            <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">Services:</h3>
            <div className="space-y-1">
                {instructor.services.map((service) => (
                <div key={service.id} className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">{service.skill}</span>
                    <span className="text-sm font-medium">${service.hourly_rate}/hr</span>
                </div>
                ))}
            </div>
            </div>

            {/* Areas of Service */}
            <div className="mb-4">
            <p className="text-xs text-gray-500">
                Areas: {instructor.areas_of_service.join(", ")}
            </p>
            </div>

            {/* Replace the pricing/experience section (lines ~130-133) with: */}
            <div className="flex justify-between items-center mb-4 text-sm text-gray-600">
            <span>{instructor.years_experience} years exp.</span>
            <span className="text-xs">
                From ${Math.min(...instructor.services.map(s => s.hourly_rate))}/hr
            </span>
            </div>

            <button
              onClick={() => router.push(`/instructors/${instructor.user_id}`)}
              className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 transition-colors"
            >
              View Profile
            </button>
          </div>
        ))}
      </div>

      {filteredInstructors.length === 0 && (
        <div className="text-center text-gray-500 mt-8">
          No instructors found matching your search.
        </div>
      )}
    </div>
    </>
  );
}
