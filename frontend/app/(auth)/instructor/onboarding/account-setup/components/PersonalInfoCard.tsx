'use client';

import { ChevronDown, User as UserIcon } from 'lucide-react';
import type { ProfileFormState } from '@/features/instructor-profile/types';

type PersonalInfoCardProps = {
  context?: 'dashboard' | 'onboarding';
  profile: ProfileFormState;
  onProfileChange: (updates: Partial<ProfileFormState>) => void;
  isOpen?: boolean;
  onToggle?: () => void;
};

export function PersonalInfoCard({
  context = 'dashboard',
  profile,
  onProfileChange,
  isOpen = true,
  onToggle,
}: PersonalInfoCardProps) {
  const isOnboarding = context === 'onboarding';
  const collapsible = !isOnboarding && typeof onToggle === 'function';
  const expanded = collapsible ? Boolean(isOpen) : true;

  const header = (
    <div className="w-full flex items-center justify-between text-left">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
          <UserIcon className="w-6 h-6 text-[#7E22CE]" />
        </div>
        <div className="flex flex-col text-left">
          <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Personal Information</span>
          <span className="text-sm text-gray-500">Basic details that appear on your profile and booking receipts.</span>
        </div>
      </div>
      {collapsible && (
        <ChevronDown
          className={`w-5 h-5 text-gray-600 transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      )}
    </div>
  );

  const handleChange = (field: keyof ProfileFormState, value: string) => {
    onProfileChange({ [field]: value } as Partial<ProfileFormState>);
  };

  return (
    <section className="bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
      {collapsible ? (
        <button
          type="button"
          className="w-full flex items-center justify-between mb-4 text-left"
          onClick={onToggle}
          aria-expanded={expanded}
        >
          {header}
        </button>
      ) : (
        <div className="mb-4">{header}</div>
      )}

      {expanded && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="py-2">
            <label htmlFor="first_name" className="text-gray-600 mb-2 block">First Name</label>
            <input
              id="first_name"
              type="text"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500 bg-white autofill-fix"
              placeholder="John"
              value={profile.first_name}
              onChange={(e) => handleChange('first_name', e.target.value)}
            />
          </div>
          <div className="py-2">
            <label htmlFor="last_name" className="text-gray-600 mb-2 block">Last Name</label>
            <input
              id="last_name"
              type="text"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500 bg-white autofill-fix"
              placeholder="Smith"
              value={profile.last_name}
              onChange={(e) => handleChange('last_name', e.target.value)}
            />
          </div>
          <div className="py-2">
            <label htmlFor="postal_code" className="text-gray-600 mb-2 block">ZIP Code</label>
            <input
              id="postal_code"
              type="text"
              inputMode="numeric"
              maxLength={5}
              pattern="\\d{5}"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500 bg-white autofill-fix"
              placeholder="10001"
              value={profile.postal_code}
              onChange={(e) => {
                const digits = e.target.value.replace(/\D/g, '').slice(0, 5);
                handleChange('postal_code', digits);
              }}
              onKeyDown={(e) => {
                const allowed = ['Backspace', 'Delete', 'Tab', 'ArrowLeft', 'ArrowRight', 'Home', 'End'];
                if (!/[0-9]/.test(e.key) && !allowed.includes(e.key)) {
                  e.preventDefault();
                }
              }}
            />
          </div>
        </div>
      )}
    </section>
  );
}
