"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, MessageCircle, Calendar } from "lucide-react";
import { fetchAPI } from '@/lib/api';

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

export default function InstructorProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [instructor, setInstructor] = useState<Instructor | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    const fetchInstructor = async () => {
      try {
        const response = await fetchAPI(`/instructors/${id}`);
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error("Instructor not found");
          }
          throw new Error("Failed to fetch instructor profile");
        }
        const data = await response.json();
        setInstructor(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "An error occurred");
      } finally {
        setIsLoading(false);
      }
    };

    fetchInstructor();
  }, [id]);

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
        <div className="text-center">
          <h2 className="text-2xl font-bold text-red-500 mb-2">Error</h2>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={() => router.push("/instructors")}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Browse
          </button>
        </div>
      </div>
    );
  }

  if (!instructor) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-8">
        {/* Back Button */}
        <button
          onClick={() => router.push("/instructors")}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-8"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Browse
        </button>

        <div className="bg-white rounded-xl shadow-lg overflow-hidden">
          {/* Header Section */}
          <div className="p-8 border-b">
            <h1 className="text-3xl font-bold mb-4">{instructor.user.full_name}</h1>
            <div className="flex flex-wrap gap-4 text-gray-600">
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                Areas: {instructor.areas_of_service.join(", ")}
              </div>
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {instructor.years_experience} years experience
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="p-8">
            {/* Services & Pricing Section */}
            <div className="mb-8">
              <h2 className="text-xl font-semibold mb-4">Services & Pricing</h2>
              <div className="space-y-3">
                {instructor.services.map((service) => (
                  <div key={service.id} className="flex justify-between items-start p-4 bg-gray-50 rounded-lg">
                    <div>
                      <h3 className="font-medium text-gray-900">{service.skill}</h3>
                      {service.description && (
                        <p className="text-sm text-gray-600 mt-1">{service.description}</p>
                      )}
                    </div>
                    <div className="text-lg font-semibold text-blue-600">
                      ${service.hourly_rate}/hr
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Bio Section */}
            <div className="mb-8">
              <h2 className="text-xl font-semibold mb-4">About</h2>
              <p className="text-gray-700 leading-relaxed">{instructor.bio}</p>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-col sm:flex-row gap-4">
              <button
                onClick={() => console.log("Book session clicked")}
                className="flex-1 flex items-center justify-center gap-2 bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors"
              >
                <Calendar className="h-5 w-5" />
                Book a Session
              </button>
              <button
                onClick={() => console.log("Message clicked")}
                className="flex-1 flex items-center justify-center gap-2 bg-white border border-gray-300 text-gray-700 px-6 py-3 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <MessageCircle className="h-5 w-5" />
                Message Instructor
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}