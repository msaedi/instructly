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
  minBioChars?: number;
  maxBioChars?: number;
  showMinCharHint?: boolean;
  showCharCount?: boolean;
  showRewriteButton?: boolean;
  bioLabel?: string;
  bioPlaceholder?: string;
  yearsLabel?: string;
  yearsMin?: number;
  yearsMax?: number;
  allowEmptyYears?: boolean;
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
  minBioChars = 400,
  maxBioChars,
  showMinCharHint = true,
  showCharCount = false,
  showRewriteButton = true,
  bioLabel = 'Introduce Yourself',
  bioPlaceholder = 'Highlight your experience, favorite teaching methods, and the type of students you enjoy working with.',
  yearsLabel = 'Years of Experience',
  yearsMin = 1,
  yearsMax = 70,
  allowEmptyYears = false,
}: BioCardProps) {
  const isOnboarding = context === 'onboarding';
  const collapsible = context !== 'onboarding' && typeof onToggle === 'function';
  const expanded = collapsible ? Boolean(isOpen) : true;
  const cardClassName = isOnboarding
    ? 'insta-surface-card p-4 sm:p-6'
    : 'bg-white rounded-none border-0 p-4 sm:rounded-lg sm:border sm:border-gray-200 sm:p-6 insta-surface-card';
  const showInlinePhotoUpload = embedded || isOnboarding;
  const showBioWarning = showMinCharHint && bioTouched && bioTooShort;
  const yearsValue = allowEmptyYears && profile.years_experience === 0 ? '' : profile.years_experience;

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
    if (allowEmptyYears && value.trim().length === 0) {
      onProfileChange({ years_experience: 0 });
      return;
    }
    const parsed = parseInt(value || '0', 10);
    if (Number.isNaN(parsed)) {
      onProfileChange({ years_experience: yearsMin });
      return;
    }
    const next = Math.max(yearsMin, Math.min(yearsMax, parsed));
    onProfileChange({ years_experience: next });
  };

  return (
    <section className={cardClassName}>
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
            <p className="text-gray-600 mt-1">{bioLabel}</p>
          </div>
          <div>
            <div className="relative">
              <textarea
                rows={4}
                className={`w-full rounded-md border px-3 py-2 pr-16 pb-8 text-sm focus:outline-none ${showBioWarning ? 'border-red-300 focus:border-red-500' : 'border-gray-300 focus:border-purple-500'}`}
                placeholder={bioPlaceholder}
                value={profile.bio}
                onChange={(e) => onProfileChange({ bio: e.target.value })}
                onBlur={() => setBioTouched(true)}
                maxLength={maxBioChars}
              />
              {showMinCharHint && minBioChars > 0 && (
                <div className="pointer-events-none absolute bottom-2 right-3 text-[10px] text-gray-500 z-10 bg-white/80 px-1">
                  Minimum {minBioChars} characters
                </div>
              )}
            </div>
            {showMinCharHint && bioTooShort && (
              <div className="mt-1 text-xs text-red-600">Your bio is under {minBioChars} characters. You can still save and complete it later.</div>
            )}
            {showCharCount && (
              <div className="mt-1 text-xs text-gray-500">
                {profile.bio.length}{maxBioChars ? `/${maxBioChars}` : ''} characters
              </div>
            )}
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label htmlFor="details_years_experience" className="block text-sm text-gray-600 mb-1">{yearsLabel}</label>
                <input
                  id="details_years_experience"
                  type="number"
                  min={yearsMin}
                  max={yearsMax}
                  step={1}
                  inputMode="numeric"
                  value={yearsValue}
                  onKeyDown={(e) => { if ([".", ",", "e", "E", "+", "-"].includes(e.key)) { e.preventDefault(); } }}
                  onChange={(e) => handleYearsChange(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-center font-medium focus:outline-none focus:ring-2 focus:ring-[#7E22CE]/20 focus:border-purple-500 no-spinner"
                />
              </div>
            </div>
            {showRewriteButton && (
              <div className="mt-3 flex justify-end">
                <button
                  type="button"
                  onClick={onGenerateBio}
                  className="inline-flex items-center justify-center px-3 py-1.5 rounded-md text-sm sm:text-xs bg-[#7E22CE] text-white shadow-sm hover:bg-[#7E22CE]"
                >
                  Rewrite with AI
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
