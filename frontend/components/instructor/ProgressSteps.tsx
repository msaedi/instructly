'use client';

import { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { setProfileCacheNormalized } from '@/features/instructor-onboarding/profileCache';

type StepState = {
  step1Complete: boolean;
  step2Complete: boolean;
  step3Complete: boolean;
  step4Complete: boolean;
};

export function ProgressSteps(_: { currentStep: 1 | 2 | 3 | 4 }) {
  const [state, setState] = useState<StepState | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [meRes, profileRes, areasRes, addrsRes] = await Promise.all([
          fetchWithAuth(API_ENDPOINTS.ME),
          fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE),
          fetchWithAuth('/api/addresses/service-areas/me'),
          fetchWithAuth('/api/addresses/me'),
        ]);
        const me = meRes.ok ? await meRes.json() : {};
        const profile = profileRes.ok ? await profileRes.json() : {};
        setProfileCacheNormalized('ProgressHeader:GET', profile);
        const areas = areasRes.ok ? await areasRes.json() : { items: [] };

        // Resolve a postal code from multiple sources for robustness
        let defaultZip = '';
        try {
          if (addrsRes && addrsRes.ok) {
            const list = await addrsRes.json();
            const def = (list.items || []).find((a: unknown) => (a as Record<string, unknown>)['is_default']) || (list.items || [])[0];
            defaultZip = String((def as Record<string, unknown>)?.['postal_code'] || '').trim();
          }
        } catch {}
        const zipFromUser = String((me?.zip_code || me?.postal_code || '') as string).trim();
        const zipFromProfile = String((profile?.postal_code || '') as string).trim();
        const resolvedPostal = zipFromProfile || zipFromUser || defaultZip;

        const hasPic = Boolean(me?.has_profile_picture) || Number.isFinite(me?.profile_picture_version);
        const personalInfo = Boolean((me?.first_name || '').trim()) && Boolean((me?.last_name || '').trim()) && Boolean(resolvedPostal);
        const bioOk = (String(profile?.bio || '').trim().length) >= 400;
        const hasServiceArea = Array.isArray(areas?.items) && areas.items.length > 0;
        const step1Complete = hasPic && personalInfo && bioOk && hasServiceArea;

        const services: Array<{ hourly_rate?: number | string }> = Array.isArray(profile?.services) ? profile.services : [];
        const step2Complete = services.some((s) => Number(s?.hourly_rate || 0) > 0);

        const step3Complete = Boolean(profile?.identity_verified_at || profile?.identity_verification_session_id);
        const step4Complete = Boolean(profile?.stripe_connect_enabled || (profile?.charges_enabled && profile?.payouts_enabled));

        setState({ step1Complete, step2Complete, step3Complete, step4Complete });
      } catch {
        setState({ step1Complete: false, step2Complete: false, step3Complete: false, step4Complete: false });
      }
    };
    void load();
  }, []);

  const dashed = {
    backgroundImage: 'repeating-linear-gradient(to right, #7E22CE 0, #7E22CE 8px, transparent 8px, transparent 16px)'
  } as const;

  const renderStep = (label: string, complete: boolean) => (
    <div className="flex items-center">
      <div className="flex flex-col items-center relative">
        <div className="w-6 h-6 rounded-full border-2 border-[#7E22CE] bg-[#7E22CE] flex items-center justify-center">
          {complete ? <Check className="w-3 h-3 text-white" /> : <X className="w-3 h-3 text-white" />}
        </div>
        <span className="text-[10px] text-gray-600 mt-1 whitespace-nowrap absolute top-7">{label}</span>
      </div>
    </div>
  );

  const renderConnector = (leftComplete: boolean) => (
    <div className="w-60 h-0.5" style={leftComplete ? { backgroundColor: '#7E22CE' } : dashed} />
  );

  const s = state || { step1Complete: false, step2Complete: false, step3Complete: false, step4Complete: false };

  return (
    <div className="absolute left-1/2 transform -translate-x-1/2 items-center gap-0 hidden min-[1400px]:flex">
      {renderStep('Account Setup', s.step1Complete)}
      {renderConnector(s.step1Complete)}
      {renderStep('Add Skills', s.step2Complete)}
      {renderConnector(s.step2Complete)}
      {renderStep('Verify Identity', s.step3Complete)}
      {renderConnector(s.step3Complete)}
      {renderStep('Payment Setup', s.step4Complete)}
    </div>
  );
}
