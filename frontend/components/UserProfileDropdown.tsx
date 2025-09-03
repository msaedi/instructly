'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { User, Calendar, LogOut, ChevronDown, AlertCircle } from 'lucide-react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { createPortal } from 'react-dom';
import { RoleName } from '@/types/enums';
import { UserAvatar } from '@/components/user/UserAvatar';
import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';

export default function UserProfileDropdown() {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0 });
  const [instructorOnboardingComplete, setInstructorOnboardingComplete] = useState(true);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Ensure component only renders on client
  useEffect(() => {
    setIsMounted(true);
  }, []);

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

    checkOnboardingStatus();
  }, [user]);

  // Calculate dropdown position
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + window.scrollY + 8,
        left: rect.right - 180 + window.scrollX, // Right-aligned, 180px width for longer text
      });
    }
  }, [isOpen]);

  // Handle clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
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
    logout();
  };

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
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 hover:bg-gray-100 rounded-full pr-2 pl-1 py-1 transition-colors"
      >
        <UserAvatar user={user as { id: string; first_name?: string; last_name?: string; has_profile_picture?: boolean; profile_picture_version?: number } | null} size={48} />
        <ChevronDown className={`h-4 w-4 text-purple-600 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && typeof window !== 'undefined' && createPortal(
        <div
          ref={dropdownRef}
          className="bg-white rounded-lg shadow-xl border border-gray-200 py-2 w-[180px] animate-fadeIn"
          style={{
            position: 'absolute',
            top: `${dropdownPosition.top}px`,
            left: `${dropdownPosition.left}px`,
            zIndex: 10000,
          }}
        >
          {/* Menu items */}
          <div className="py-1">
            {/* Different menu for instructors vs students */}
            {(user?.roles || []).includes(RoleName.INSTRUCTOR) ? (
              // Instructor menu
              <button
                onClick={() => handleNavigation(
                  instructorOnboardingComplete ? '/instructor/dashboard' : '/instructor/onboarding/skill-selection'
                )}
                className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {instructorOnboardingComplete ? (
                  <>
                    <User className="h-4 w-4" />
                    Dashboard
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-4 w-4 text-purple-600" />
                    <span className="text-[#6A0DAD] font-medium">Finish Onboarding</span>
                  </>
                )}
              </button>
            ) : (
              // Student menu
              <>
                <button
                  onClick={() => handleNavigation('/student/dashboard')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <User className="h-4 w-4" />
                  My Account
                </button>

                <button
                  onClick={() => handleNavigation('/student/lessons')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  <Calendar className="h-4 w-4" />
                  My Lessons
                </button>
              </>
            )}

            <hr className="my-1 border-gray-100" />

            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-[#6A0DAD] hover:bg-purple-50 transition-colors"
            >
              <LogOut className="h-4 w-4" />
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
