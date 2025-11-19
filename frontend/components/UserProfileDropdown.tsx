'use client';

import { useState, useRef, useEffect, useCallback, useLayoutEffect, type ReactNode, type CSSProperties } from 'react';
import { useRouter } from 'next/navigation';
import { User, Calendar, LogOut, ChevronDown, Gift } from 'lucide-react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { createPortal } from 'react-dom';
import { RoleName } from '@/types/enums';
import { UserAvatar } from '@/components/user/UserAvatar';
import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { STEP_KEYS } from '@/lib/onboardingSteps';

const ONBOARDING_SHORTCUTS: Array<{
  key: keyof OnboardingStatusMap;
  label: string;
  href: string;
  testId: string;
}> = [
  { key: 'account-setup', label: 'Account setup', href: '/instructor/onboarding/account-setup', testId: 'menu-onboarding-account-setup' },
  { key: 'skill-selection', label: 'Skills & pricing', href: '/instructor/onboarding/skill-selection', testId: 'menu-onboarding-skill-selection' },
  { key: 'verify-identity', label: 'Verify identity', href: '/instructor/onboarding/verification', testId: 'menu-onboarding-verify-identity' },
  { key: 'payment-setup', label: 'Payment setup', href: '/instructor/onboarding/payment-setup', testId: 'menu-onboarding-payment-setup' },
];
import type { OnboardingStatusMap } from '@/lib/onboardingSteps';

interface UserProfileDropdownProps {
  hideDashboardItem?: boolean;
  onToggle?: (open: boolean) => void;
  inlineMode?: boolean;
  inlinePanelContainer?: HTMLDivElement | null;
  onboardingStatusMap?: OnboardingStatusMap;
  inlineExtraContent?: (closeMenu: () => void) => ReactNode;
}

export default function UserProfileDropdown({
  hideDashboardItem = false,
  onToggle,
  inlineMode = false,
  inlinePanelContainer,
  onboardingStatusMap,
  inlineExtraContent,
}: UserProfileDropdownProps) {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, right: 0 });
  const [instructorOnboardingCompleteFallback, setInstructorOnboardingCompleteFallback] = useState(true);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inlineContentRef = useRef<HTMLDivElement | null>(null);
  const [inlineContentHeight, setInlineContentHeight] = useState(0);
  const isInline = inlineMode;
  const isInstructor = (user?.roles || []).includes(RoleName.INSTRUCTOR);
  const resolvedOnboardingComplete = onboardingStatusMap
    ? STEP_KEYS.every((key) => onboardingStatusMap[key]?.completed)
    : instructorOnboardingCompleteFallback;
  const shouldShowOnboardingShortcuts = Boolean(isInstructor && onboardingStatusMap && !resolvedOnboardingComplete);
  const closeDropdown = useCallback(() => {
    setIsOpen((prev) => {
      if (!prev) return prev;
      onToggle?.(false);
      return false;
    });
  }, [onToggle]);

  const toggleDropdown = () => {
    setIsOpen((prev) => {
      const next = !prev;
      onToggle?.(next);
      return next;
    });
  };



  // Ensure component only renders on client
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // No-op viewport effect (reverted to desktop-style dropdown only)

  // Check instructor onboarding status when no shared status map is provided
  useEffect(() => {
    if (onboardingStatusMap) return;
    const checkOnboardingStatus = async () => {
      if (user && (user.roles || []).includes(RoleName.INSTRUCTOR)) {
        try {
          const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
          if (response.ok) {
            const profile = await response.json();
            const isComplete =
              profile.is_live === true ||
              (profile.stripe_connect_enabled === true &&
                profile.identity_verified_at !== null &&
                profile.services &&
                profile.services.length > 0);
            setInstructorOnboardingCompleteFallback(isComplete);
          }
        } catch {
          setInstructorOnboardingCompleteFallback(false);
        }
      }
    };

    void checkOnboardingStatus();
  }, [user, onboardingStatusMap]);

  // Calculate dropdown position and handle open/close side-effects
  useEffect(() => {
    if (!isOpen || isInline || !buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    setDropdownPosition({
      top: rect.bottom + window.scrollY + 8,
      right: window.innerWidth - (rect.right + window.scrollX),
    });
  }, [isOpen, isInline]);

  // Remove ResizeObserver/spacer logic to restore stable behavior

  // Handle clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const targetNode = event.target as Node;
      const clickedInsideDesktop = buttonRef.current ? buttonRef.current.contains(targetNode) : false;
      const clickedInsideDropdown = dropdownRef.current ? dropdownRef.current.contains(targetNode) : false;
      if (!clickedInsideDesktop && !clickedInsideDropdown) {
        closeDropdown();
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, closeDropdown]);

  const handleNavigation = (path: string) => {
    closeDropdown();
    router.push(path);
  };

  const handleLogout = () => {
    closeDropdown();
    void logout();
  };

  const showDashboardShortcut = resolvedOnboardingComplete && !hideDashboardItem;

  useLayoutEffect(() => {
    if (!isInline) return;
    const measure = () => {
      if (inlineContentRef.current) {
        setInlineContentHeight(inlineContentRef.current.scrollHeight);
      }
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [isInline, showDashboardShortcut, shouldShowOnboardingShortcuts, user, hideDashboardItem, isOpen, onboardingStatusMap]);

  const renderMenuContent = (variant: 'inline' | 'popover') => {
    const neutralButtonClasses =
      variant === 'inline'
        ? 'w-full flex items-center gap-2 px-2 py-2 text-sm text-gray-700 hover:text-[#7E22CE] transition-colors'
        : 'w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors';
    const onboardingButtonClasses =
      variant === 'inline'
        ? 'w-full flex items-center px-2 py-1.5 text-sm font-medium text-[#7E22CE] hover:text-[#5B1D9B] transition-colors'
        : 'w-full flex items-center px-3 py-2 text-sm font-medium text-[#7E22CE] hover:bg-purple-50 transition-colors';
    const logoutButtonClasses =
      variant === 'inline'
        ? 'w-full flex items-center gap-2 px-2 py-2 text-sm text-[#7E22CE]'
        : 'w-full flex items-center gap-2 px-3 py-2 text-sm text-[#7E22CE] hover:bg-purple-50 transition-colors';
    const wrapperClass = variant === 'inline' ? 'flex flex-col gap-1.5 w-full' : 'py-0.5';
    const onboardingGroupClass =
      variant === 'inline'
        ? 'flex flex-col gap-1 w-full border-b border-purple-100/70 pb-2 mb-2'
        : 'flex flex-col gap-0.5 border-b border-gray-100 pb-2 mb-2';

    return (
      <div className={`${wrapperClass} ${variant === 'inline' ? 'bg-white/95 rounded-2xl shadow-md p-3' : ''}`}>
        {shouldShowOnboardingShortcuts && (
          <div className={onboardingGroupClass} role="group" aria-label="Onboarding shortcuts">
            {ONBOARDING_SHORTCUTS.map((shortcut) => (
              <button
                key={shortcut.key}
                onClick={() => handleNavigation(shortcut.href)}
                className={onboardingButtonClasses}
                data-testid={shortcut.testId}
                aria-label={`Go to ${shortcut.label}`}
              >
                {shortcut.label}
              </button>
            ))}
          </div>
        )}

        {isInstructor ? (
          <>
            {showDashboardShortcut && (
              <button
                onClick={() =>
                  handleNavigation(
                    resolvedOnboardingComplete ? '/instructor/dashboard' : '/instructor/onboarding/skill-selection',
                  )
                }
                className={neutralButtonClasses}
                aria-label="Go to dashboard"
              >
                <>
                  <User className="h-4 w-4" aria-hidden="true" />
                  Dashboard
                </>
              </button>
            )}
          </>
        ) : (
          <>
            <button onClick={() => handleNavigation('/student/dashboard')} className={neutralButtonClasses}>
              <User className="h-4 w-4" aria-hidden="true" />
              My Account
            </button>

            <button
              onClick={() => handleNavigation('/student/dashboard?tab=rewards')}
              className={neutralButtonClasses}
            >
              <Gift className="h-4 w-4" aria-hidden="true" />
              Rewards
            </button>

            <button onClick={() => handleNavigation('/student/lessons')} className={neutralButtonClasses}>
              <Calendar className="h-4 w-4" aria-hidden="true" />
              My Lessons
            </button>
          </>
        )}

        {variant === 'inline' && inlineExtraContent && (
          <div className="mt-3 border-t border-purple-100/60 pt-3 w-full">
            {inlineExtraContent(closeDropdown)}
          </div>
        )}

        <button onClick={handleLogout} className={logoutButtonClasses}>
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Sign Out
        </button>
      </div>
    );
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

  const inlinePanelStyles: CSSProperties | undefined = isInline
    ? {
        maxHeight: isOpen ? `${inlineContentHeight}px` : '0px',
        opacity: isOpen ? 1 : 0,
        transform: isOpen ? 'translateY(0)' : 'translateY(-8px)',
        pointerEvents: isOpen ? 'auto' : 'none',
      }
    : undefined;

  const assignInlineRef = (node: HTMLDivElement | null) => {
    inlineContentRef.current = node;
    dropdownRef.current = node;
  };

  const inlineMenu =
    isInline && inlinePanelContainer
      ? createPortal(
          <div
            className="w-full overflow-hidden transition-[max-height,opacity,transform] duration-200 ease-out will-change-[max-height]"
            style={inlinePanelStyles}
            aria-hidden={!isOpen}
          >
            <div ref={assignInlineRef} className="w-full">
              {renderMenuContent('inline')}
            </div>
          </div>,
          inlinePanelContainer,
        )
      : null;

  const popoverMenu =
    !isInline && isOpen && typeof window !== 'undefined'
      ? createPortal(
          <div
            ref={dropdownRef}
            className="bg-white border border-gray-200 py-1 rounded-lg shadow-xl animate-fadeIn inline-block"
            style={{
              position: 'absolute',
              top: dropdownPosition.top,
              right: dropdownPosition.right,
              zIndex: 10000,
              width: 'auto',
              minWidth: '140px',
            }}
          >
            {renderMenuContent('popover')}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className={isInline ? 'w-full flex flex-col items-end gap-2' : undefined}>
      <button
        ref={buttonRef}
        onClick={toggleDropdown}
        className={`inline-flex items-center justify-center gap-2 rounded-full pr-4 pl-3 py-2 transition-colors mr-0 focus:outline-none ${
          isInline ? 'focus-visible:ring-0 focus-visible:ring-offset-0' : 'focus-visible:ring-2 focus-visible:ring-[#C084FC] focus-visible:ring-offset-2'
        }`}
        aria-label={isOpen ? 'Close user menu' : 'Open user menu'}
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <UserAvatar
          user={user as { id: string; first_name?: string; last_name?: string; has_profile_picture?: boolean; profile_picture_version?: number } | null}
          size={48}
        />
        {!isInline && (
          <ChevronDown
            className={`h-4 w-4 text-purple-600 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            aria-hidden="true"
          />
        )}
      </button>

      {isInline ? inlineMenu : popoverMenu}

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
    </div>
  );
}
