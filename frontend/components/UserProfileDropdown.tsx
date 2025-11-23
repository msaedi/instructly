'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { User, Calendar, LogOut, ChevronDown, AlertCircle, Gift } from 'lucide-react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { createPortal } from 'react-dom';
import { RoleName } from '@/types/enums';
import { UserAvatar } from '@/components/user/UserAvatar';
import { useInstructorProfileMe } from '@/hooks/queries/useInstructorProfileMe';

interface UserProfileDropdownProps {
  hideDashboardItem?: boolean;
}

export default function UserProfileDropdown({ hideDashboardItem = false }: UserProfileDropdownProps) {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, right: 0 });
  const [isMobileViewport] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const isInstructor = (user?.roles || []).includes(RoleName.INSTRUCTOR);
  const { data: instructorProfile } = useInstructorProfileMe(isInstructor && isMounted);
  const instructorOnboardingComplete = useMemo(() => {
    if (!isInstructor) return true;
    if (!instructorProfile) return false;
    const services = Array.isArray(instructorProfile.services) ? instructorProfile.services : [];
    const stripeEnabled = Boolean(
      (instructorProfile as { stripe_connect_enabled?: boolean }).stripe_connect_enabled
    );
    const identityVerified =
      Boolean((instructorProfile as { identity_verified_at?: string | null }).identity_verified_at) ||
      Boolean(
        (instructorProfile as { identity_verification_session_id?: string | null })
          .identity_verification_session_id
      );
    return (
      instructorProfile.is_live === true ||
      (stripeEnabled && identityVerified && services.length > 0)
    );
  }, [instructorProfile, isInstructor]);



  // Ensure component only renders on client
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // No-op viewport effect (reverted to desktop-style dropdown only)

  // Calculate dropdown position and handle open/close side-effects
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + window.scrollY + 8,
        right: window.innerWidth - (rect.right + window.scrollX),
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
          className={`bg-white border border-gray-200 py-1 rounded-lg shadow-xl animate-fadeIn inline-block`}
          style={{ position: 'absolute', top: dropdownPosition.top, right: dropdownPosition.right, zIndex: 10000, width: 'auto', minWidth: '140px' }}
        >
          {/* Menu items */}
          <div className={`${isMobileViewport ? 'py-1' : 'py-0.5'}`}>
            {/* Different menu for instructors vs students */}
            {(user?.roles || []).includes(RoleName.INSTRUCTOR) ? (
              // Instructor menu
              <>
                {showDashboardShortcut && (
                  <button
                    onClick={() => handleNavigation(
                      instructorOnboardingComplete ? '/instructor/dashboard' : '/instructor/onboarding/skill-selection'
                    )}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
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

              </>
            ) : (
              // Student menu
              <>
                <button
                  onClick={() => handleNavigation('/student/dashboard')}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <User className="h-4 w-4" aria-hidden="true" />
                  My Account
                </button>

                <button
                  onClick={() => handleNavigation('/student/dashboard?tab=rewards')}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <Gift className="h-4 w-4" aria-hidden="true" />
                  Rewards
                </button>

                <button
                  onClick={() => handleNavigation('/student/lessons')}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <Calendar className="h-4 w-4" aria-hidden="true" />
                  My Lessons
                </button>
              </>
            )}

            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[#7E22CE] hover:bg-purple-50 transition-colors"
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
