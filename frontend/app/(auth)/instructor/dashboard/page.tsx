// frontend/app/(auth)/instructor/dashboard/page.tsx
'use client';

import { BRAND } from '@/app/config/brand';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { Edit, Calendar, ExternalLink, LogOut, Trash2, CheckCircle2, XCircle } from 'lucide-react';
import EditProfileModal from '@/components/modals/EditProfileModal';
import DeleteProfileModal from '@/components/modals/DeleteProfileModal';
import { fetchWithAuth, API_ENDPOINTS, getConnectStatus } from '@/lib/api';
import { logger } from '@/lib/logger';
import { InstructorProfile, getInstructorDisplayName } from '@/types/instructor';
import { useAuth } from '@/features/shared/hooks/useAuth';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import StripeOnboarding from '@/components/instructor/StripeOnboarding';

export default function InstructorDashboardNew() {
  const router = useRouter();
  const { logout } = useAuth();
  const [profile, setProfile] = useState<InstructorProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [connectStatus, setConnectStatus] = useState<any>(null);

  const fetchProfile = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      logger.warn('No access token found, redirecting to login');
      router.push('/login?redirect=/instructor/dashboard');
      return;
    }

    try {
      logger.info('Fetching instructor profile');
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);

      if (response.status === 404) {
        logger.warn('No instructor profile found');
        setError('No instructor profile found. Please complete your profile setup.');
        setIsLoading(false);
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to fetch profile');
      }

      const data: InstructorProfile = await response.json();
      if (!data.user || !data.services) {
        logger.error('Invalid profile data structure', undefined, { data });
        throw new Error('Invalid profile data received');
      }

      logger.info('Instructor profile loaded successfully', {
        userId: data.user_id,
        servicesCount: data.services.length,
        areasCount: data.areas_of_service?.length || 0,
      });

      setProfile(data);
    } catch (err) {
      logger.error('Error fetching instructor profile', err);
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    logger.info('Instructor dashboard (new) loaded');
    fetchProfile();
    (async () => {
      try {
        const s = await getConnectStatus();
        setConnectStatus(s);
      } catch (e) {
        logger.warn('Failed to load connect status');
      }
    })();
  }, [router]);

  // Gate access until cleared to go live
  useEffect(() => {
    if (!profile || connectStatus == null) return;
    const skillsOk = (profile.skills_configured === true) || (Array.isArray(profile.services) && profile.services.length > 0);
    const identityOk = Boolean(profile.identity_verified_at || profile.identity_verification_session_id);
    const connectOk = Boolean(connectStatus && connectStatus.onboarding_completed);
    const ready = skillsOk && identityOk && connectOk;
    if (!ready) {
      logger.info('Redirecting to onboarding status - prerequisites not complete');
      router.replace('/instructor/onboarding/status');
    }
  }, [profile, connectStatus, router]);

  const handleLogout = () => {
    logger.info('Instructor logging out');
    logout();
  };

  const handleProfileUpdate = () => {
    logger.info('Profile updated, refreshing data');
    fetchProfile();
    setShowEditModal(false);
  };

  const handleProfileDelete = () => {
    logger.info('Instructor profile deleted, logging out and redirecting home');
    logout();
    router.push('/');
  };

  const handleViewPublicProfile = () => {
    if (profile) {
      logger.debug('Navigating to public profile', { userId: profile.user_id });
      router.push(`/instructors/${profile.user_id}`);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-700"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="sticky top-0 z-50 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="container mx-auto px-6">
            <div className="flex justify-between items-center h-16">
              <Link href="/" className="text-2xl font-bold text-purple-700">
                {BRAND.name}
              </Link>
              <UserProfileDropdown />
            </div>
          </div>
        </header>
        <div className="container mx-auto px-6 py-12">
          <div className="bg-white rounded-lg shadow p-6 text-center">
            <h2 className="text-2xl font-bold text-red-600 mb-4">Error</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <Link
              href="/signup?redirect=%2Finstructor%2Fonboarding%2Fstep-2"
              className="inline-block px-6 py-2 bg-purple-700 text-white rounded-md hover:bg-purple-800 transition-colors"
              onClick={() => logger.debug('Navigating to signup with redirect to step-2 from error state')}
            >
              Complete Profile Setup
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!profile) return null;

  const displayName = getInstructorDisplayName(profile);

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <a href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">{BRAND.name}</h1>
          </a>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header */}
        <div className="bg-white rounded-lg p-6 mb-6 border border-gray-200">
          <h1 className="text-3xl font-bold text-gray-600 mb-2">Welcome back, {profile.user?.first_name || 'Instructor'}!</h1>
          <p className="text-gray-600">Manage your instructor profile and payouts</p>
        </div>

        {/* Quick Actions */}
        <div className="mb-6 flex flex-wrap gap-4">
          <Link
            href="/instructor/availability"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <Calendar className="h-4 w-4" />
            <span>Manage Availability</span>
          </Link>
          <Link
            href="/instructor/bookings"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <Calendar className="h-4 w-4" />
            <span>View Bookings</span>
          </Link>
          <button
            onClick={handleViewPublicProfile}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-gray-200 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            <span>View Public Profile</span>
          </button>
        </div>

        <div className="mb-8 grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Stripe Status Card */}
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-2">Stripe Account Status</h2>
            <p className="text-gray-600 text-sm mb-4">Your Stripe account setup status.</p>
            <div className="rounded-lg border border-green-200 bg-green-50 p-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm text-green-900">
                <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Charges enabled</div>
                <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Payouts enabled</div>
                <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Details verified</div>
                <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Ready for payments</div>
              </div>
            </div>
            <div className="mt-4">
              <button
                onClick={async () => {
                  try { const s = await getConnectStatus(); setConnectStatus(s); } catch {}
                }}
                className="inline-flex items-center px-3 py-2 text-sm rounded-md border border-gray-300 bg-white hover:bg-gray-50"
              >
                <ExternalLink className="w-4 h-4 mr-2 rotate-90" /> Refresh Status
              </button>
            </div>
          </div>

          {/* Stripe Payouts Link */}
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-2">Stripe Payouts</h2>
            <p className="text-gray-600 text-sm mb-3">Access your Stripe Express dashboard to view payouts and account settings.</p>
            <Link
              href="#"
              onClick={async (e) => {
                e.preventDefault();
                try {
                  const resp = await getConnectStatus();
                  if (resp?.onboarding_completed) {
                    const dl = await fetchWithAuth('/api/payments/connect/dashboard');
                    if (dl.ok) {
                      const data = await dl.json();
                      window.open(data.dashboard_url, '_blank');
                    }
                  } else {
                    alert('Your Stripe onboarding is not completed yet.');
                  }
                } catch {
                  alert('Unable to open Stripe dashboard right now.');
                }
              }}
              className="text-purple-700 hover:underline"
            >
              Open payouts dashboard →
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Total Bookings</h3>
            <p className="text-3xl font-bold text-purple-700">0</p>
            <p className="text-sm text-gray-500 mt-1">Coming soon</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Rating</h3>
            <p className="text-3xl font-bold text-purple-700">-</p>
            <p className="text-sm text-gray-500 mt-1">Not yet available</p>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Total Earnings</h3>
            <p className="text-3xl font-bold text-purple-700">$0</p>
            <p className="text-sm text-gray-500 mt-1">Payment integration pending</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Link
            href="/instructor/availability"
            className="block p-6 bg-white rounded-lg shadow hover:shadow-lg transition-shadow"
            onClick={() => logger.debug('Navigating to availability management')}
          >
            <div className="flex items-center gap-4">
              <Calendar className="w-8 h-8 text-purple-700" />
              <div>
                <h3 className="text-lg font-semibold">Manage Availability</h3>
                <p className="text-gray-600">Set your weekly schedule and available hours</p>
              </div>
            </div>
          </Link>
          <div className="p-6 bg-gray-100 rounded-lg border-2 border-dashed border-gray-300">
            <div className="text-center text-gray-500">
              <p className="font-semibold">More features coming soon</p>
              <p className="text-sm mt-1">Booking management, analytics, and more</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm p-6 mb-8">
          <div className="flex justify-between items-start mb-6">
            <h2 className="text-xl font-bold text-gray-900">Profile Information</h2>
            <button
              onClick={() => {
                logger.debug('Opening edit profile modal');
                setShowEditModal(true);
              }}
              className="flex items-center px-4 py-2 bg-purple-700 text-white rounded-md hover:bg-purple-800 transition-colors"
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
                      {service.description && <p className="text-sm text-gray-600">{service.description}</p>}
                    </div>
                    <span className="font-semibold text-purple-700">${service.hourly_rate}/hr</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-sm font-medium text-gray-500 mb-1">Areas of Service</h3>
                <p className="text-gray-900">{profile.areas_of_service.join(', ')}</p>
              </div>
              <div>
                <h3 className="text-sm font-medium text-gray-500 mb-1">Experience</h3>
                <p className="text-gray-900">{profile.years_experience} years</p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-4">
          <button
            onClick={handleViewPublicProfile}
            className="flex items-center px-6 py-3 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 transition-colors"
          >
            <ExternalLink className="h-5 w-5 mr-2" />
            View Public Profile
          </button>
          <button
            onClick={() => {
              logger.debug('Opening delete profile modal');
              setShowDeleteModal(true);
            }}
            className="flex items-center px-6 py-3 bg-red-50 border border-red-300 text-red-700 rounded-md hover:bg-red-100 transition-colors"
          >
            <Trash2 className="h-5 w-5 mr-2" />
            Delete Instructor Profile
          </button>
          <button
            onClick={async () => {
              try {
                const res = await fetchWithAuth('/api/payments/connect/instant-payout', { method: 'POST' });
                if (!res.ok) {
                  const err = await res.json().catch(() => ({} as any));
                  alert(`Instant payout failed: ${err.detail || res.statusText}`);
                  return;
                }
                const data = await res.json();
                alert(`Instant payout requested: ${data.payout_id || 'OK'}`);
              } catch (e) {
                alert('Instant payout request error');
              }
            }}
            className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            Request Instant Payout
          </button>
        </div>
      </div>

      {showEditModal && (
        <EditProfileModal isOpen={showEditModal} onClose={() => setShowEditModal(false)} onSuccess={handleProfileUpdate} />
      )}
      {showDeleteModal && (
        <DeleteProfileModal isOpen={showDeleteModal} onClose={() => setShowDeleteModal(false)} onSuccess={handleProfileDelete} />
      )}
    </div>
  );
}

function ChecklistRow({ label, ok, action }: { label: string; ok: boolean; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border border-gray-100 rounded-md px-4 py-3">
      <div className="flex items-center gap-2">
        {ok ? <CheckCircle2 className="w-5 h-5 text-green-600" /> : <XCircle className="w-5 h-5 text-gray-300" />}
        <span className="text-gray-800">{label}</span>
      </div>
      <div>{action}</div>
    </div>
  );
}
