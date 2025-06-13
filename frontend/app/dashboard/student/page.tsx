"use client";

import { BRAND } from '@/app/config/brand'
// app/dashboard/student/page.tsx

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Calendar, Search, LogOut } from "lucide-react";
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
// Import the new booking API
import { bookingsApi } from '@/lib/api/bookings';
import { Booking } from '@/types/booking';

interface UserData {
  id: number;
  email: string;
  full_name: string;
  role: string;
}

export default function StudentDashboard() {
  const router = useRouter();
  const [userData, setUserData] = useState<UserData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Add state for bookings
  const [upcomingBookings, setUpcomingBookings] = useState<Booking[]>([]);
  const [bookingsLoading, setBookingsLoading] = useState(true);

  useEffect(() => {
    const fetchUserData = async () => {
      const token = localStorage.getItem("access_token");
      if (!token) {
        router.push("/login");
        return;
      }

      try {
        const response = await fetchWithAuth(API_ENDPOINTS.ME);

        if (!response.ok) {
          throw new Error("Failed to fetch user data");
        }

        const data = await response.json();
        if (data.role !== "student") {
          router.push("/dashboard/instructor");
          return;
        }
        
        setUserData(data);
        // Once we have user data, fetch bookings
        fetchBookings();
      } catch (err) {
        console.error("Error fetching user data:", err);
        router.push("/login");
      } finally {
        setIsLoading(false);
      }
    };

    fetchUserData();
  }, [router]);

  // Fetch bookings for the student
  const fetchBookings = async () => {
    try {
      const myBookings = await bookingsApi.getMyBookings({ 
        upcoming: true,
        per_page: 10 
      });
      
      // If we have bookings, store them
      if (myBookings.bookings && Array.isArray(myBookings.bookings)) {
        setUpcomingBookings(myBookings.bookings);
      }
    } catch (error) {
      console.error('Error fetching bookings:', error);
    } finally {
      setBookingsLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    router.push("/");
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  if (!userData) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link href="/" className="text-2xl font-bold text-indigo-600">
              {BRAND.name}
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
        {/* Welcome Section */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Welcome back, {userData.full_name}!
          </h1>
          <p className="text-gray-600">Find and book sessions with expert instructors</p>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Link href="/instructors" className="block">
            <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center">
                <Search className="h-8 w-8 text-indigo-600 mr-4" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Find Instructors</h3>
                  <p className="text-gray-600">Browse and search for instructors</p>
                </div>
              </div>
            </div>
          </Link>

          <Link href="/dashboard/student/bookings" className="block">
            <div className="bg-white rounded-lg shadow-sm p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center">
                <Calendar className="h-8 w-8 text-indigo-600 mr-4" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">My Bookings</h3>
                  <p className="text-gray-600">View and manage your sessions</p>
                </div>
              </div>
            </div>
          </Link>
        </div>

        {/* Upcoming Sessions */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Upcoming Sessions</h2>
          
          {bookingsLoading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-indigo-500 mx-auto"></div>
              <p className="text-gray-500 mt-2">Loading bookings...</p>
            </div>
          ) : upcomingBookings.length > 0 ? (
            <div className="space-y-4">
              {upcomingBookings.slice(0, 3).map((booking) => (
                <div key={booking.id} className="border rounded-lg p-4 hover:bg-gray-50">
                  <div className="flex justify-between items-start">
                    <div>
                      <h4 className="font-semibold text-gray-900">{booking.service_name}</h4>
                      <p className="text-sm text-gray-600">
                        with {booking.instructor?.full_name || 'Instructor'}
                      </p>
                      <p className="text-sm text-gray-500 mt-1">
                        {new Date(booking.booking_date).toLocaleDateString('en-US', {
                          weekday: 'long',
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric'
                        })} at {booking.start_time.slice(0, 5)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-gray-900">${booking.total_price}</p>
                      <span className="inline-flex px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">
                        {booking.status}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
              
              {upcomingBookings.length > 3 && (
                <Link
                  href="/dashboard/student/bookings"
                  className="block text-center text-indigo-600 hover:text-indigo-700 font-medium"
                >
                  View all {upcomingBookings.length} bookings →
                </Link>
              )}
            </div>
          ) : (
            <>
              <p className="text-gray-500 text-center py-8">No upcoming sessions booked yet</p>
              <div className="text-center">
                <Link
                  href="/instructors"
                  className="inline-block px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
                >
                  Find an Instructor
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}