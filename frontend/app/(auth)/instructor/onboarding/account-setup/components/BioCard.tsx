'use client';

import { BookOpen, Camera, ChevronDown } from 'lucide-react';
import { ProfilePictureUpload } from '@/components/user/ProfilePictureUpload';
import type { ProfileFormState } from '@/features/instructor-profile/types';

type BioCardProps = {
  context?: 'dashboard' | 'onboarding';
  embedded?: boolean;
  profile: ProfileFormState;
  onProfileChange: (updates: Partial<ProfileFormState>) => void;
  bioTouched: boolean;
  bioTooShort: boolean;
  setBioTouched: (next: boolean) => void;
  isOpen?: boolean;
  onToggle?: () => void;
  onGenerateBio: () => void;
};

export function BioCard({
  context = 'dashboard',
  embedded = false,
  profile,
  onProfileChange,
  bioTouched,
  bioTooShort,
  setBioTouched,
  isOpen = true,
  onToggle,
  onGenerateBio,
}: BioCardProps) {
  const isOnboarding = context === 'onboarding';
  const collapsible = context !== 'onboarding' && typeof onToggle === 'function';
  const expanded = collapsible ? Boolean(isOpen) : true;
  const showInlinePhotoUpload = embedded || isOnboarding;

  const header = (
    <div className="w-full flex items-center justify-between text-left">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-purple-100 flex items-center justify-center">
          <BookOpen className="w-6 h-6 text-[#7E22CE]" />
        </div>
        <div className="flex flex-col text-left">
          <span className="text-xl sm:text-lg font-bold sm:font-semibold text-gray-900">Profile Details</span>
          <span className="text-sm text-gray-500">Tell students about your experience, style, and teaching approach.</span>
        </div>
      </div>
      {collapsible && (
        <ChevronDown className={`w-5 h-5 text-gray-600 transition-transform ${expanded ? 'rotate-180' : ''}`} />
      )}
    </div>
  );

  const handleYearsChange = (value: string) => {
    const n = Math.max(1, Math.min(70, parseInt(value || '0', 10)));
    onProfileChange({ years_experience: Number.isNaN(n) ? 1 : n });
  };

  return (
    <section className="bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6">
      {collapsible ? (
        <button type="button" className="w-full flex items-center justify-between mb-4 text-left" onClick={onToggle} aria-expanded={expanded}>
          {header}
        </button>
      ) : (
        <div className="mb-4">{header}</div>
      )}

      {expanded && (
        <div className="py-2">
          {showInlinePhotoUpload && (
            <div className="mb-4">
              <ProfilePictureUpload
                size={101}
                ariaLabel="Upload profile photo"
                trigger={
                  <div
                    className="w-[101px] h-[101px] rounded-full bg-purple-100 flex items-center justify-center hover:bg-purple-200 cursor-pointer transition-transform duration-150 ease-in-out hover:scale-[1.02]"
                    title="Upload profile photo"
                  >
                    <Camera className="w-7 h-7 text-[#7E22CE]" />
                  </div>
                }
              />
            </div>
          )}
          <div className="mb-2">
            <p className="text-gray-600 mt-1">Introduce Yourself</p>
          </div>
          <div>
            <div className="relative">
              <textarea
                rows={4}
                className={`w-full rounded-md border px-3 py-2 pr-16 pb-8 text-sm focus:outline-none ${bioTouched && bioTooShort ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-purple-500'}`}
                placeholder="Highlight your experience, favorite teaching methods, and the type of students you enjoy working with."
                value={profile.bio}
                onChange={(e) => onProfileChange({ bio: e.target.value })}
                onBlur={() => setBioTouched(true)}
              />
              <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] text-gray-500 z-10 bg-white/80 px-1">
                Minimum 400 characters
              </div>
            </div>
            {bioTooShort && (
              <div className="mt-1 text-xs text-red-600">Your bio is under 400 characters. You can still save and complete it later.</div>
            )}
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label htmlFor="details_years_experience" className="block text-sm text-gray-600 mb-1">Years of Experience</label>
                <input
                  id="details_years_experience"
                  type="number"
                  min={1}
                  max={70}
                  step={1}
                  inputMode="numeric"
                  value={profile.years_experience}
                  onKeyDown={(e) => { if ([".", ",", "e", "E", "+", "-"].includes(e.key)) { e.preventDefault(); } }}
                  onChange={(e) => handleYearsChange(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 no-spinner"
                />
              </div>
            </div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                onClick={onGenerateBio}
                className="inline-flex items-center justify-center px-3 py-1.5 rounded-md text-sm sm:text-xs bg-[#7E22CE] text-white shadow-sm hover:bg-[#7E22CE]"
              >
                Rewrite with AI
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
