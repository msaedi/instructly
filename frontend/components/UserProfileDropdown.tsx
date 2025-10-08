'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { User, Calendar, LogOut, ChevronDown, AlertCircle, Gift, Menu } from 'lucide-react';
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
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  // kept for potential future offset adjustments when headers vary in height
  const [, setMobileTop] = useState(0);
  const [mobileSlotEl, setMobileSlotEl] = useState<HTMLElement | null>(null);
  const [mobileMenuHeight, setMobileMenuHeight] = useState<number>(0);
  const [instructorOnboardingComplete, setInstructorOnboardingComplete] = useState(true);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const mobileTriggerRef = useRef<HTMLDivElement>(null);

  // Ensure component only renders on client
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Track viewport for mobile-specific dropdown behavior
  useEffect(() => {
    const update = () => {
      const isMobile = typeof window !== 'undefined' && window.innerWidth < 640;
      setIsMobileViewport(isMobile);
      const header = typeof document !== 'undefined' ? document.querySelector('header') : null;
      const headerHeight = header ? (header as HTMLElement).getBoundingClientRect().height : 56;
      setMobileTop(headerHeight);
      // Create or fetch a slot right after the header for mobile accordion pushdown
      if (typeof document !== 'undefined') {
        let slot = document.getElementById('mobile-dropdown-slot');
        if (!slot) {
          slot = document.createElement('div');
          slot.id = 'mobile-dropdown-slot';
          // Insert at very top so it covers the header and pushes content down via body padding
          document.body.prepend(slot);
        }
        setMobileSlotEl(slot);
      }
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
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

    void checkOnboardingStatus();
  }, [user]);

  // Calculate dropdown position and handle open/close side-effects
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const vw = window.innerWidth;
      const isMobile = vw < 640;
      if (isMobile) {
        // Mobile: pin to top of the page (just under status bar), right-aligned with 8px margin
        const width = 180; // keep same width as menu
        const left = window.scrollX + Math.max(8, vw - (width + 8));
        setDropdownPosition({
          top: window.scrollY + 8,
          left,
        });
      } else {
        // Desktop: position under trigger, right-aligned
        setDropdownPosition({
          top: rect.bottom + window.scrollY + 8,
          left: rect.right - 180 + window.scrollX,
        });
      }
    }
    if (isMobileViewport) {
      if (isOpen) {
        // Defer to next frame to ensure content is mounted before measuring
        requestAnimationFrame(() => {
          const h = dropdownRef.current?.scrollHeight || 0;
          setMobileMenuHeight(h);
          document.body.style.paddingTop = `${h}px`;
        });
      } else {
        // Closing: collapse and remove top padding
        setMobileMenuHeight(0);
        document.body.style.paddingTop = '';
      }
    }
  }, [isOpen, isMobileViewport]);

  // Handle clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const targetNode = event.target as Node;
      const clickedInsideDesktop = buttonRef.current ? buttonRef.current.contains(targetNode) : false;
      const clickedInsideMobile = mobileTriggerRef.current ? mobileTriggerRef.current.contains(targetNode) : false;
      const clickedInsideDropdown = dropdownRef.current ? dropdownRef.current.contains(targetNode) : false;
      if (!clickedInsideDesktop && !clickedInsideMobile && !clickedInsideDropdown) {
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
      {/* Mobile trigger: div to avoid iOS button tap overlay */}
      <div
        ref={mobileTriggerRef}
        className="sm:hidden no-tap-highlight inline-flex items-center justify-center rounded-full pr-0 pl-1 py-1 mr-0 select-none"
        role="button"
        tabIndex={0}
        aria-label={isOpen ? 'Close user menu' : 'Open user menu'}
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setIsOpen(!isOpen); } }}
      >
        <Menu className="h-6 w-6 text-[#7E22CE] pointer-events-none select-none" aria-hidden="true" />
      </div>

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
          className={`bg-white border border-gray-200 ${isMobileViewport ? 'w-full rounded-none border-b shadow-md overflow-hidden transition-[max-height,opacity] duration-500 ease-in-out' : 'py-2 w-[180px] rounded-lg shadow-xl animate-fadeIn'}`}
          style={isMobileViewport ? { position: 'fixed', top: 0, left: 0, right: 0, zIndex: 10000, maxHeight: mobileMenuHeight } : { position: 'absolute', top: dropdownPosition.top, left: dropdownPosition.left, zIndex: 10000 }}
        >
          {/* Menu items */}
          <div className={`${isMobileViewport ? 'py-2' : 'py-1'}`}>
            {/* Different menu for instructors vs students */}
            {(user?.roles || []).includes(RoleName.INSTRUCTOR) ? (
              // Instructor menu
              <>
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

                {/* Onboarding quick links (desktop/web and mobile alike) */}
                <div className="my-1 border-t border-gray-100" />
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
                  onClick={() => handleNavigation('/rewards')}
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
        isMobileViewport && mobileSlotEl ? mobileSlotEl : document.body
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
