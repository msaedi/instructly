"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react"; 
import Link from "next/link";
import { Edit, Calendar, ExternalLink, LogOut, Trash2 } from "lucide-react";
import EditProfileModal from "@/components/EditProfileModal";
import DeleteProfileModal from "@/components/DeleteProfileModal";
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';


interface InstructorProfile {
  id: number;
  user_id: number;
  bio: string;
  areas_of_service: string[];
  years_experience: number;
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

export default function InstructorDashboard() {
  const router = useRouter();
  const [profile, setProfile] = useState<InstructorProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);


  const fetchProfile = async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      router.push("/login?redirect=/dashboard/instructor");
      return;
    }
  
    try {
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
  
      if (response.status === 404) {
        setError("No instructor profile found. Please complete your profile setup.");
        setIsLoading(false);
        return;
      }
  
      if (!response.ok) {
        throw new Error("Failed to fetch profile");
      }
  
      const data = await response.json();
      
      // Make sure we have the expected data structure
      if (!data.user || !data.services) {
        console.error("Invalid profile data structure:", data);
        throw new Error("Invalid profile data received");
      }
      
      setProfile(data);
    } catch (err) {
      console.error("Error fetching profile:", err);
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/");
  };

  const handleProfileUpdate = () => {
    // Refresh profile data after successful update
    fetchProfile();
    setShowEditModal(false);
  };

  const handleProfileDelete = () => {
    // After successful deletion, redirect to home or student dashboard
    router.push("/dashboard/student");
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50">
        <nav className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <Link href="/" className="text-2xl font-bold text-indigo-600">
                Instructly
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center text-gray-600 hover:text-gray-900"
              >
                <LogOut className="h-5 w-5 mr-2" />
                Log out
              </button>
            </div>
          </div>
        </nav>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="bg-white rounded-lg shadow p-6 text-center">
            <h2 className="text-2xl font-bold text-red-600 mb-4">Error</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <Link
              href="/become-instructor"
              className="inline-block px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
            >
              Complete Profile Setup
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!profile) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="text-2xl font-bold text-indigo-600">
              Instructly
            </Link>
            <button
              onClick={handleLogout}
              className="flex items-center text-gray-600 hover:text-gray-900"
            >
              <LogOut className="h-5 w-5 mr-2" />
              Log out
            </button>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <Link href="/" className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-4">
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Home
      </Link>
        {/* Welcome Section */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Welcome back, {profile?.user?.full_name || profile?.user?.email || 'Instructor'}!
          </h1>
          <p className="text-gray-600">Manage your instructor profile and bookings</p>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Total Bookings</h3>
            <p className="text-3xl font-bold text-indigo-600">0</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Rating</h3>
            <p className="text-3xl font-bold text-indigo-600">-</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Total Earnings</h3>
            <p className="text-3xl font-bold text-indigo-600">$0</p>
          </div>
        </div>
        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Link
            href="/dashboard/instructor/availability"
            className="block p-6 bg-white rounded-lg shadow hover:shadow-lg transition-shadow"
          >
            <div className="flex items-center gap-4">
              <Calendar className="w-8 h-8 text-indigo-600" />
              <div>
                <h3 className="text-lg font-semibold">Manage Availability</h3>
                <p className="text-gray-600">Set your weekly schedule and available hours</p>
              </div>
            </div>
          </Link>
          {/* Add more quick action cards here later */}
        </div>
        {/* Profile Section */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <div className="flex justify-between items-start mb-6">
            <h2 className="text-xl font-bold text-gray-900">Profile Information</h2>
            <button
              onClick={() => setShowEditModal(true)}
              className="flex items-center px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
            >
              <Edit className="h-4 w-4 mr-2" />
              Edit Profile
            </button>
          </div>

          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-1">Bio</h3>
              <p className="text-gray-900">{profile.bio}</p>
            </div>

            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2">Services & Pricing</h3>
              <div className="space-y-2">
                {profile.services.map((service) => (
                  <div key={service.id} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                    <div>
                      <span className="font-medium">{service.skill}</span>
                      {service.description && (
                        <p className="text-sm text-gray-600">{service.description}</p>
                      )}
                    </div>
                    <span className="font-semibold text-indigo-600">${service.hourly_rate}/hr</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-sm font-medium text-gray-500 mb-1">Areas of Service</h3>
                <p className="text-gray-900">{profile.areas_of_service.join(", ")}</p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-gray-500 mb-1">Experience</h3>
                <p className="text-gray-900">{profile.years_experience} years</p>
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap gap-4">
          <button
            onClick={() => router.push(`/instructors/${profile.user_id}`)}
            className="flex items-center px-6 py-3 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50"
          >
            <ExternalLink className="h-5 w-5 mr-2" />
            View Public Profile
          </button>
          <button
            onClick={() => setShowDeleteModal(true)}
            className="flex items-center px-6 py-3 bg-red-50 border border-red-300 text-red-700 rounded-md hover:bg-red-100"
            >
            <Trash2 className="h-5 w-5 mr-2" />
            Delete Instructor Profile
          </button>
        </div>
      </div>
      {/* Modals */}
      {showEditModal && (
        <EditProfileModal
          isOpen={showEditModal}
          onClose={() => setShowEditModal(false)}
          onSuccess={handleProfileUpdate}
        />
      )}
      {showDeleteModal && (
        <DeleteProfileModal
            isOpen={showDeleteModal}
            onClose={() => setShowDeleteModal(false)}
            onSuccess={handleProfileDelete}
        />
      )}
    </div>
  );
}