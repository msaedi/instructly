'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { User, Calendar, LogOut, ChevronDown } from 'lucide-react';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { createPortal } from 'react-dom';

export default function UserProfileDropdown() {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Ensure component only renders on client
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Get user initials
  const getInitials = () => {
    if (!user) return 'G'; // Guest
    const firstInitial = user.first_name?.[0] || '';
    const lastInitial = user.last_name?.[0] || '';
    return (firstInitial + lastInitial).toUpperCase() || 'U';
  };

  // Calculate dropdown position
  useEffect(() => {
    if (isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setDropdownPosition({
        top: rect.bottom + window.scrollY + 8,
        left: rect.right - 200 + window.scrollX, // Right-aligned, 200px width
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
      <div className="w-9 h-9 bg-gray-200 rounded-full animate-pulse" />
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
        <div className="w-9 h-9 bg-purple-700 text-white rounded-full flex items-center justify-center font-semibold text-sm">
          {getInitials()}
        </div>
        <ChevronDown className={`h-4 w-4 text-gray-600 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && typeof window !== 'undefined' && createPortal(
        <div
          ref={dropdownRef}
          className="bg-white rounded-lg shadow-xl border border-gray-200 py-2 w-[200px] animate-fadeIn"
          style={{
            position: 'absolute',
            top: `${dropdownPosition.top}px`,
            left: `${dropdownPosition.left}px`,
            zIndex: 10000,
          }}
        >
          {/* User info */}
          <div className="px-4 py-2 border-b border-gray-100">
            <p className="text-sm font-medium text-gray-900">
              {user.first_name} {user.last_name}
            </p>
            <p className="text-xs text-gray-500">{user.email}</p>
          </div>

          {/* Menu items */}
          <div className="py-1">
            <button
              onClick={() => handleNavigation('/dashboard/student')}
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

            <hr className="my-1 border-gray-100" />

            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
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
