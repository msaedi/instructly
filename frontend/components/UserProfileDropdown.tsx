'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { User, Calendar, LogOut, ChevronDown, AlertCircle, Gift } from 'lucide-react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { createPortal } from 'react-dom';
import { RoleName } from '@/types/enums';
import { UserAvatar } from '@/components/user/UserAvatar';
import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';

interface UserProfileDropdownProps {
  hideDashboardItem?: boolean;
}

export default function UserProfileDropdown({ hideDashboardItem = false }: UserProfileDropdownProps) {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0 });
  const [isMobileViewport] = useState(false);
  const [instructorOnboardingComplete, setInstructorOnboardingComplete] = useState(true);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);



  // Ensure component only renders on client
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // No-op viewport effect (reverted to desktop-style dropdown only)

  // Check instructor onboarding status
  useEffect(() => {
    const checkOnboardingStatus = async () => {
      if (user && (user.roles || []).includes(RoleName.INSTRUCTOR)) {
        try {
          const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
          if (response.ok) {
            const profile = await response.json();
            // Check if all onboarding steps are complete
            const isComplete =
              profile.is_live === true ||
              (profile.stripe_connect_enabled === true &&
               profile.identity_verified_at !== null &&
               profile.services && profile.services.length > 0);
            setInstructorOnboardingComplete(isComplete);
          }
        } catch {
          // If we can't fetch profile, assume onboarding incomplete
          setInstructorOnboardingComplete(false);
        }
      }
    };

    void checkOnboardingStatus();
  }, [user]);

  // Calculate dropdown position and handle open/close side-effects
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + window.scrollY + 8,
        left: rect.right - 180 + window.scrollX,
      });
    }
  }, [isOpen]);

  // Remove ResizeObserver/spacer logic to restore stable behavior

  // Handle clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const targetNode = event.target as Node;
      const clickedInsideDesktop = buttonRef.current ? buttonRef.current.contains(targetNode) : false;
      const clickedInsideDropdown = dropdownRef.current ? dropdownRef.current.contains(targetNode) : false;
      if (!clickedInsideDesktop && !clickedInsideDropdown) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleNavigation = (path: string) => {
    setIsOpen(false);
    router.push(path);
  };

  const handleLogout = () => {
    setIsOpen(false);
    void logout();
  };

  const showDashboardShortcut = !(hideDashboardItem && instructorOnboardingComplete);

  // Don't render until mounted to avoid hydration mismatch
  if (!isMounted || isLoading) {
    return (
      <div className="animate-pulse">
        <div className="w-10 h-10 bg-gray-200 rounded-full"></div>
      </div>
    );
  }

  if (!user) {
    // Show login button for guests
    return (
      <button
        onClick={() => router.push('/login')}
        className="text-gray-600 hover:text-gray-900 px-4 py-2 text-sm font-medium"
      >
        Sign In
      </button>
    );
  }

  return (
    <>
      {/* Mobile trigger removed during rollback */}

      {/* Desktop trigger */}
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        className="hidden sm:inline-flex items-center justify-center gap-2 rounded-full pr-2 pl-1 py-1 transition-colors mr-0 focus:outline-none"
        aria-label={isOpen ? 'Close user menu' : 'Open user menu'}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <UserAvatar user={user as { id: string; first_name?: string; last_name?: string; has_profile_picture?: boolean; profile_picture_version?: number } | null} size={48} />
        <ChevronDown
          className={`h-4 w-4 text-purple-600 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {isOpen && typeof window !== 'undefined' && createPortal(
        <div
          ref={dropdownRef}
          className={`bg-white border border-gray-200 py-2 w-[180px] rounded-lg shadow-xl animate-fadeIn`}
          style={{ position: 'absolute', top: dropdownPosition.top, left: dropdownPosition.left, zIndex: 10000 }}
        >
          {/* Menu items */}
          <div className={`${isMobileViewport ? 'py-2' : 'py-1'}`}>
            {/* Different menu for instructors vs students */}
            {(user?.roles || []).includes(RoleName.INSTRUCTOR) ? (
              // Instructor menu
              <>
                {showDashboardShortcut && (
                  <button
                    onClick={() => handleNavigation(
                      instructorOnboardingComplete ? '/instructor/dashboard' : '/instructor/onboarding/skill-selection'
                    )}
                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    {instructorOnboardingComplete ? (
                      <>
                        <User className="h-4 w-4" aria-hidden="true" />
                        Dashboard
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-4 w-4 text-purple-600" aria-hidden="true" />
                        <span className="text-[#7E22CE] font-medium whitespace-nowrap">Finish Onboarding</span>
                      </>
                    )}
                  </button>
                )}

                {/* Onboarding quick links (desktop/web and mobile alike) */}
                <div className={showDashboardShortcut ? 'my-1 border-t border-gray-100' : 'my-1'} />
                <div className="px-4 py-1 text-[10px] uppercase tracking-wide text-gray-400">Onboarding</div>
                <button
                  onClick={() => handleNavigation('/instructor/profile')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Account setup
                </button>
                <button
                  onClick={() => handleNavigation('/instructor/onboarding/skill-selection')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Add skills
                </button>
                <button
                  onClick={() => handleNavigation('/instructor/onboarding/verification')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Verify identity
                </button>
                <button
                  onClick={() => handleNavigation('/instructor/onboarding/payment-setup')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Payment setup
                </button>
              </>
            ) : (
              // Student menu
              <>
                <button
                  onClick={() => handleNavigation('/student/dashboard')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <User className="h-4 w-4" aria-hidden="true" />
                  My Account
                </button>

                <button
                  onClick={() => handleNavigation('/student/dashboard?tab=rewards')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <Gift className="h-4 w-4" aria-hidden="true" />
                  Rewards
                </button>

                <button
                  onClick={() => handleNavigation('/student/lessons')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <Calendar className="h-4 w-4" aria-hidden="true" />
                  My Lessons
                </button>
              </>
            )}

            <hr className="my-1 border-gray-100" />

            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-[#7E22CE] hover:bg-purple-50 transition-colors"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Sign Out
            </button>
          </div>
        </div>,
        document.body
      )}

      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-8px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        .animate-fadeIn {
          animation: fadeIn 0.2s ease-out;
        }
      `}</style>
    </>
  );
}
